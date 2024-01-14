from flask import Flask, render_template, request, redirect
from dotenv import load_dotenv
from flask_cors import CORS
from bson.objectid import ObjectId
from datetime import datetime
import pprint, locale, os, pymongo, sqlite3
from babel.numbers import format_currency as fcrr

# Load environment variables from .env file
load_dotenv()

# helper functions
def open_DB(db):
    connection=sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    return connection
def format_currency(amount, currency='IDR'):  # Default currency is Indonesian Rupiah (IDR)
    formatted_amount = fcrr(amount, currency, locale='id_ID.UTF-8')
    return formatted_amount
def filter_orders_by_dates(orders, target_dates):
    return [order for order in orders if order['deliveryDate'] in target_dates]
def calculate_order_total(po):
    order_total = 0.0
    for product in po['products'] + po['hampers']:
        price_value = product['price_value']
        quantity = product['quantity']
        discount_value = product['discount'] * product['price_value'] / 100.0
        item_subtotal = (price_value - discount_value) * quantity
        order_total += item_subtotal
    return order_total

# objects creation
app = Flask(__name__)
database_key = os.environ["MONGOKEY"]
MCString = "mongodb+srv://salmonkarp:" + database_key + "@cookieskingdomdb.gq6eh6v.mongodb.net/"
MClient = pymongo.MongoClient(MCString)['CK']
app.jinja_env.filters['format_currency'] = format_currency
CORS(app)  # Enable CORS for all routes and origins

# Configure FLASK_DEBUG from environment variable
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG')

# home
@app.route("/",methods=["GET"])
def root():
    return render_template('menu.html')

# add product get
@app.route("/add_product",methods=["GET"])
def add_product():
    return render_template("add_product.html")

# modify details
@app.route("/modify",methods=["GET"])
def modify():
    return render_template("modify.html")

# add hampers get
@app.route("/add_hampers",methods=["GET"])
def add_hampers():
    ckProducts = MClient['Products']
    showIDProjection = {
        '_id':True,
        'name':True
    }
    productsList = list(ckProducts.find({},showIDProjection))
    return render_template("add_hampers.html",productsList=productsList)

# add product post
@app.route("/submit_addition",methods=["POST"])
def add_product_submit():
    product_type = request.form.get('product-type')
    ckProducts = MClient['Products']
    new_product = {
        'name': request.form.get('name'),
        'currentStock': int(request.form['currentStock']),
        'prices':[]
    }
    
    # Extract price names and values from the form
    price_names = request.form.getlist('priceName[]')
    price_values = request.form.getlist('priceValue[]')

    # Create a list of dictionaries for prices
    for name, value in zip(price_names, price_values):
        new_product['prices'].append({
            'name': name,
            'value': float(value)
        })
    ckProducts.insert_one(new_product)
    return redirect('/edit_product')

# add hampers post
@app.route("/submit_addition_hampers",methods=["POST"])
def add_hampers_submit():
    hamper_name = request.form.get('hname')
    selected_products = request.form.getlist('products[]')
    ckHampers = MClient['Hampers']
    
    # Extract price names and values from the form
    price_names = request.form.getlist('priceName[]')
    price_values = request.form.getlist('priceValue[]')
    
    hamper = {
        'name': hamper_name,
        'prices': [],
        'items': []
    }

    for product_id in selected_products:
        quantity_key = 'quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        
        if quantity > 0:
            hamper['items'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity
            })
    for name, value in zip(price_names, price_values):
        hamper['prices'].append({
            'name': name,
            'value': float(value)
        })
        
    # Insert the new hamper into the MongoDB database
    ckHampers.insert_one(hamper)
    return redirect('/edit_hamper')

# view object get
@app.route("/edit_product",methods=["GET"])
def edit_view_product():
    productsList = list(MClient['Products'].find().sort('name',pymongo.ASCENDING))
    return render_template("edit_view_product.html", productsList = productsList)

# view object get
@app.route("/edit_hamper",methods=["GET"])
def edit_view_hamper():
    ckHampers = MClient['Hampers']
    pipeline = pipeline = [
        {
            '$lookup': {
                'from': 'Products',
                'localField': 'items.product_id',
                'foreignField': '_id',
                'as': 'itemsDetails'
            }
        },
        {
            '$unwind': '$itemsDetails'
        },
        {
            '$project': {
                '_id': 1,
                'name': 1,
                'prices':1,
                'item': {
                    'product_id': '$itemsDetails._id',
                    'quantity': {'$arrayElemAt': ['$items.quantity', {'$indexOfArray': ['$items.product_id', '$itemsDetails._id']}]},
                    'name': '$itemsDetails.name'
                }
            }
        },
        {
            '$group': {
                '_id': {
                    '_id': '$_id',
                    'name': '$name',
                    'prices':'$prices'
                },
                'items': {
                    '$push': '$item'
                }
            }
        },
        {
            '$project': {
                '_id': '$_id._id',
                'name': '$_id.name',
                'prices': '$_id.prices',
                'items': 1
            }
        },
        {
            '$sort':{
                'name':pymongo.ASCENDING
            }
        }
    ]

    hampersList = list(ckHampers.aggregate(pipeline))
    return render_template("edit_view_hamper.html", hampersList = hampersList)

# edit product get
@app.route("/edit_product/<productID>",methods=["GET"])
def edit_product(productID):
    ckConn = MClient['Products']
    itemDetails = ckConn.find_one({
        '_id':ObjectId(productID)
    })
    return render_template('edit_product.html',product = itemDetails)

# handle edit product post
@app.route("/edit_product_submit/<productID>", methods=["POST"])
def edit_product_submit(productID):
    ckConn = MClient['Products']
    updated_name = request.form['name']
    updated_current_stock = int(request.form['currentStock'])
    
    # Process existing prices from the form
    prices = []
    for i in range(len(request.form.getlist('priceName'))):
        price_name = request.form.getlist('priceName')[i]
        price_value = float(request.form.getlist('priceValue')[i])
        prices.append({"name": price_name, "value": price_value})
    
    # Update the product data
    ckConn.update_many({
        '_id':ObjectId(productID)
    },{
        '$set':{
            'name':updated_name,
            'currentStock':updated_current_stock,
            'prices': prices
        }
    })
    return redirect('/edit_product')

# handle delete product get
@app.route("/delete_product/<productID>",methods=["GET"])
def delete_product(productID):
    ckConn = MClient['Products']
    ckConn.delete_many({
        '_id':ObjectId(productID)
    })
    return redirect('/edit_product')

# edit hampers get
@app.route("/edit_hampers/<hampersID>",methods=["GET"])
def edit_hampers(hampersID):
    productsList = list(MClient['Products'].find())
    ckConn = MClient['Hampers']
    itemDetails = ckConn.find_one({
        '_id':ObjectId(hampersID)
    })
    QuantDict = {}
    for item in productsList:
        QuantDict[item['_id']] = 0
    for item2 in itemDetails['items']:
        tempItemID = item2['product_id']
        QuantDict[ObjectId(tempItemID)] = item2['quantity']
        print('added',item2['quantity'])
    print(QuantDict)
    return render_template('edit_hampers.html',hamper = itemDetails, productsList = productsList, QuantDict = QuantDict)

@app.route("/edit_hampers_submit/<hampersID>",methods=["POST"])
def edit_hampers_submit(hampersID):
    ckHampers = MClient['Hampers']
    hamper_name = request.form.get('hname')
    all_products = list(MClient['Products'].find())
    hamper = {
        'name': hamper_name,
        'prices': [],
        'items': []
    }

    for product in all_products:
        product_id = str(product['_id'])
        quantity_key = 'quantity_' + product_id
        new_quantity = int(request.form.get(quantity_key, 0))
        if new_quantity != 0:
            hamper['items'].append({
                'product_id': ObjectId(product_id),
                'product_name': product['name'],
                'quantity': new_quantity
            })
    
    for i in range(len(request.form.getlist('priceName'))):
        price_name = request.form.getlist('priceName')[i]
        price_value = float(request.form.getlist('priceValue')[i])
        hamper['prices'].append({"name": price_name, "value": price_value})
    
    ckHampers.update_one({
        '_id': ObjectId(hampersID),
    },{
        '$set':hamper
    })
    return redirect('/edit_hamper')

@app.route("/delete_hampers/<hampersID>",methods=["GET"])
def delete_hampers(hampersID):
    ckHampers = MClient['Hampers']
    ckHampers.delete_many({
        '_id':ObjectId(hampersID)
    })
    return redirect('/edit_hamper')

@app.route("/createPO",methods=['GET'])
def createPO():
    customersList = list(MClient['Customers'].find())
    productsList = list(MClient['Products'].find()) 
    hampersList = list(MClient['Hampers'].find())
    current_date = datetime.now().strftime("%Y-%m-%d")
    # pnhList = products and hampers List
    return render_template('create_po.html',customersList = customersList, productsList = productsList, hampersList = hampersList, current_date = current_date)

@app.route("/createPOSubmit",methods=["POST"])
def createPOSubmit():   
    #handling customers
    existingCustomerID = request.form.get('existing_customer_id')
    if existingCustomerID:
        custID = ObjectId(existingCustomerID)
    else:
        custName = request.form.get('customer_name')
        address = request.form.get('address')
        
        ckCustomers = MClient['Customers']
        ckCustomers.insert_one({
            'name':custName,
            'address':address
        })
        custID = ckCustomers.find_one({'name':custName,'address':address})['_id']

    #handling date
    deliveryDate = request.form.get('delivery_date')
    orderDiscount = float(request.form.get('order-discount'))
    
    #taking products and hampers list
    selected_products = request.form.getlist('products[]')
    selected_hampers = request.form.getlist('hampers[]')
    
    #creating basic order object
    OrderObject = {
        'custID':custID,
        'deliveryDate':deliveryDate,
        'products': [],
        'hampers':[]
    }

    if orderDiscount > 0:
        OrderObject['orderDiscount']=orderDiscount
    
    #adding products
    for product_id in selected_products:
        quantity_key = 'p_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        discount_key = product_id + '_product_discount'
        discount = float(request.form.get(discount_key, 0))
        price_type = request.form.get(product_id + '_price_type', '')
        
        if quantity > 0:
            product_object = {
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'price_type': price_type
            }
        
        if price_type=='custom':
            custom_price_key = product_id + "_custom_price"
            custom_price = float(request.form.get(custom_price_key, 0))
            product_object['custom_price'] = custom_price
        
        if discount > 0:
            product_object['discount'] = discount
        
        OrderObject['products'].append(product_object)

    #adding hampers
    for product_id in selected_hampers:
        quantity_key = 'h_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        discount_key = product_id + '_hamper_discount'
        discount = float(request.form.get(discount_key, 0))
        price_type = request.form.get(product_id + '_price_type', '')
        
        if quantity > 0:
            hamper_entry = {
            'product_id': ObjectId(product_id),
            'quantity': quantity,
            'price_type': price_type
        }
            
        if price_type == 'custom':
            custom_price_key = product_id + "_custom_price"
            custom_price = float(request.form.get(custom_price_key, 0))
            hamper_entry['custom_price'] = custom_price

        if discount > 0:
            hamper_entry['discount'] = discount
        
        OrderObject['hampers'].append(hamper_entry)

    ckPOs = MClient['POs']
    ckPOs.insert_one(OrderObject)

    print(OrderObject)
    return redirect('/')

@app.route("/viewPOs",methods=["GET","POST"])
def lookup():
    page = int(request.args.get('page', 1))
    start_index = (page - 1) * 3
    end_index = start_index + 3
    
    orders_collection = MClient['POs']
    products_collection = MClient['Products']  # Assuming this is the correct name for the Products collection
    hampers_collection = MClient['Hampers']
    customers_collection = MClient['Customers']
    
    result = []

    for order in orders_collection.find():
        customer = customers_collection.find_one({'_id': order['custID']})
        products_data = []

        for product in order.get('products', []):
            product_doc = products_collection.find_one({'_id': product['product_id']})
            price_type = product.get('price_type', 'custom')
            price_value = product['custom_price'] if price_type == 'custom' else next(
                (price['value'] for price in product_doc['prices'] if price['name'] == price_type), None
            )
            products_data.append({
                'product_name': product_doc['name'],
                'price_name': price_type,
                'price_value': price_value,
                'quantity': product.get('quantity'),
                'discount': product.get('discount', 0.0)
            })

        hampers_data = []

        for hamper in order.get('hampers', []):
            hamper_doc = hampers_collection.find_one({'_id': hamper['product_id']})
            price_type = hamper.get('price_type', 'custom')
            price_value = hamper['custom_price'] if price_type == 'custom' else next(
                (price['value'] for price in hamper_doc['prices'] if price['name'] == price_type), None
            )
            hampers_data.append({
                'hamper_name': hamper_doc['name'],
                'price_name': price_type,
                'price_value': price_value,
                'quantity': hamper.get('quantity'),
                'discount': hamper.get('discount', 0.0)
            })

        result.append({
            '_id': order['_id'],
            'customer_name': customer['name'],
            'customer_address': customer['address'],
            'deliveryDate': order['deliveryDate'],
            'products': products_data,
            'hampers': hampers_data,
            'orderDiscount': order.get('orderDiscount', 0.0)
        })

    # calculating order total :/
    for order in result:
        order['order_total'] = calculate_order_total(order)
    result_sorted = sorted(result, key=lambda x: datetime.strptime(x['deliveryDate'], '%Y-%m-%d'))
    
    # for specific date handling
    if request.method=='POST':
        if request.form.get('specificDate'):
            target_dates = [request.form.get('specificDate'),request.form.get('specificDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('startDate'):
            target_dates = [request.form.get('startDate'),request.form.get('endDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        else:
            filtered_orders = result_sorted
    else:
        filtered_orders = result_sorted
    
    pprint.PrettyPrinter(width=50).pprint(filtered_orders)
    return render_template('lookup.html',data = filtered_orders[start_index:end_index], page=page)

@app.route("/edit_po/<poID>",methods=["GET"])
def edit_po(poID):
    order_data = dict(MClient['POs'].find_one({'_id':ObjectId(poID)}))
    products_data = list(MClient['Products'].find())
    hampers_data = list(MClient['Hampers'].find())
    customer_data = dict(MClient['Customers'].find_one({'_id':order_data['custID']}))
    customersList = list(MClient['Customers'].find())
    
    # Convert the list of products in order_data to a dictionary for easier lookup
    products_in_order = {str(product['product_id']): product for product in order_data.get('products', [])}
    hampers_in_order = {str(hamper['product_id']): hamper for hamper in order_data.get('hampers', [])}
    
    # Add a quantity and custom_price field to each product based on order_data
    for product in products_data:
        product_id_str = str(product['_id'])
        product_in_order = products_in_order.get(product_id_str, {})
        
        product['quantity_in_order'] = product_in_order.get('quantity', 0)
        product['in_order'] = bool(product_in_order)  # Add in_order flag
        if product_in_order:
            product['price_type'] = product_in_order['price_type']
            if product_in_order['price_type'] == 'custom':
                product['has_custom_price'] = True
                product['custom_price_in_order'] = product_in_order.get('custom_price')
            else:
                product['has_custom_price'] = False
                price_type = product_in_order.get('price_type')
                product['custom_price_in_order'] = next((price['value'] for price in product['prices'] if price_type == price['name']), None)
                print(product['custom_price_in_order'])

    for hamper in hampers_data:
        hamper_id_str = str(hamper['_id'])
        hamper_in_order = hampers_in_order.get(hamper_id_str, {})
        
        hamper['quantity_in_order'] = hamper_in_order.get('quantity', 0)
        hamper['in_order'] = bool(hamper_in_order)  # Add in_order flag
        if hamper_in_order:
            hamper['price_type'] = hamper_in_order['price_type']
            if hamper_in_order['price_type'] == 'custom':
                hamper['has_custom_price'] = True
                hamper['custom_price_in_order'] = hamper_in_order.get('custom_price')
            else:
                hamper['has_custom_price'] = False
                price_type = hamper_in_order.get('price_type')
                hamper['custom_price_in_order'] = next((price['value'] for price in hamper['prices'] if price_type == price['name']), None)
                print(hamper['custom_price_in_order'])

    return render_template("edit_po.html",order_data = order_data, products_data = products_data, hampers_data = hampers_data, customer_data = customer_data, customersList = customersList)

@app.route("/edit_po_submit",methods=["POST"])
def edit_po_submit():
    orderID = request.form.get('orderID')
    
    #handling customer
    custID = request.form.get('custID')
    existing_customer_id = request.form.get('existing_customer_id')
    if existing_customer_id != "":
        custID = existing_customer_id
        MClient['POs'].update_one({'_id':ObjectId(orderID)},{
            '$set':{
                'custID':ObjectId(custID)
            }
        })
    else:
        customer_name = request.form.get('customer_name')
        customer_address = request.form.get('customer_address')
        print("stop",customer_name,customer_address)
        MClient['Customers'].update_one({'_id':ObjectId(custID)},{
            '$set':{
                'name':customer_name,
                'address':customer_address
            }
        })
    
    #handling delivery date and order discount
    deliveryDate = request.form.get('deliveryDate')
    orderDiscount = request.form.get('order-discount')
    if orderDiscount:
        orderDiscount = float(orderDiscount)
    else:
        orderDiscount = 0.0
    
    #taking products and hampers list
    selected_products = request.form.getlist('products[]')
    selected_hampers = request.form.getlist('hampers[]')
    
    #creating basic order object
    OrderObject = {
        'custID':ObjectId(custID),
        'deliveryDate':deliveryDate,
        'products': [],
        'hampers':[]
    }
    
    #adding products
    for product_id in selected_products:
        quantity_key = 'p_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        discount_key = product_id + '_product_discount'
        discount = float(request.form.get(discount_key, 0))
        price_type = request.form.get(product_id + '_price_type', '')
        
        if quantity > 0:
            product_object = {
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'price_type': price_type
            }
        
        if price_type=='custom':
            custom_price_key = product_id + "_custom_price"
            custom_price = float(request.form.get(custom_price_key, 0))
            product_object['custom_price'] = custom_price
        
        if discount > 0:
            product_object['discount'] = discount
        
        OrderObject['products'].append(product_object)

    #adding hampers
    for product_id in selected_hampers:
        quantity_key = 'h_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        discount_key = product_id + '_hamper_discount'
        discount = float(request.form.get(discount_key, 0))
        price_type = request.form.get(product_id + '_price_type', '')
        
        if quantity > 0:
            hamper_entry = {
            'product_id': ObjectId(product_id),
            'quantity': quantity,
            'price_type': price_type
        }
            
        if price_type == 'custom':
            custom_price_key = product_id + "_custom_price"
            custom_price = float(request.form.get(custom_price_key, 0))
            hamper_entry['custom_price'] = custom_price

        if discount > 0:
            hamper_entry['discount'] = discount
        
        OrderObject['hampers'].append(hamper_entry)
        
    #handling orderDiscount
    if orderDiscount >= 0:
        OrderObject['orderDiscount'] = orderDiscount
    
    ##end of copy
    ckPOs = MClient['POs']
    pprint.PrettyPrinter(width=50).pprint(OrderObject)   
    ckPOs.update_one({'_id':ObjectId(orderID)},{'$set':OrderObject})

    print(OrderObject)
    return redirect('/viewPOs')

@app.route("/delete_po/<poID>",methods=["GET"])
def delete_po(poID):
    MClient['POs'].delete_many({
        '_id':ObjectId(poID)
    })
    return redirect('/viewPOs')

@app.route('/summary',methods=["GET","POST"])
def summary():
    if request.method == "GET":
        return render_template('summary.html')
    else:
        startDate = request.form.get('startDate')
        endDate = request.form.get('endDate')
        OrderData = MClient['POs'].find(
            {
                'deliveryDate':{
                    '$gte':startDate,
                    '$lte':endDate
                }
            }
        )
        # sorting by products
        if request.form.get('viewType') == 'productSort':
            ProductsData = MClient['Products'].find()
            HampersData = MClient['Hampers']
            product_totals = {}
            for order in OrderData:
                for product in order.get('products',[]):
                    product_id = str(product['product_id'])
                    quantity = product['quantity']
                    product_totals[product_id] = product_totals.get(product_id, 0) + quantity
                for hamper in order.get('hampers',[]):
                    hamper_id = str(hamper['product_id'])
                    hamper_quantity = hamper['quantity']
                    hamper_details = HampersData.find_one({'_id':ObjectId(hamper_id)})
                    
                    if hamper_details:
                        hamper_products = hamper_details['items']
                    else:
                        hamper_products = []
                        
                    print(hamper_products)
                    for product in hamper_products:
                        product_id = str(product['product_id'])
                        product_quantity = product['quantity']
                        product_totals[product_id] = product_totals.get(product_id, 0) + (product_quantity * hamper_quantity)
                        
                    
            summary_data = []
            for product in ProductsData:
                product_id = str(product['_id'])
                product_name = product['name']
                total_quantity = product_totals.get(product_id,0)
                summary_data.append(
                    {
                        'name':product_name,
                        'total_quantity':total_quantity
                    }
                )
            
            return render_template('summary_product.html',data=summary_data, startDate = startDate, endDate = endDate)
        
        # sort by customer
        else:
            customer_totals = {}
            ProductsData = MClient['Products'].find()
            HampersData = MClient['Hampers']
            return render_template('summary_customer.html',data="")

if __name__ == '__main__':
    app.run()