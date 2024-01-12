from flask import Flask
from flask import render_template
from flask import request
from flask import redirect
from dotenv import load_dotenv
from flask_cors import CORS
from bson.objectid import ObjectId
from datetime import datetime
import pprint
import os
import pymongo
import sqlite3

# Load environment variables from .env file
load_dotenv()

# helper functions
def open_DB(db):
    connection=sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    return connection

pipeline = [
        {
            '$unwind': 
                {'path':'$products',
                 'preserveNullAndEmptyArrays': True
                }
        },
        {
            '$lookup': {
                'from': 'Products',
                'localField': 'products.product_id',
                'foreignField': '_id',
                'as': 'product_details'
            }
        },
        {
            '$unwind': {
                'path':'$hampers',
                 'preserveNullAndEmptyArrays': True
            }
        },
        {
            '$lookup': {
                'from': 'Hampers',
                'localField': 'hampers.product_id',
                'foreignField': '_id',
                'as': 'hamper_details'
            }
        },
        {
        "$lookup": {
                "from": "Customers",
                "localField": "custID",
                "foreignField": "_id",
                "as": "customer_details"
            }
        },
        {
            '$group': {
                '_id': '$_id',
                'order_id': {'$first': '$_id'},
                'customer_name': {"$first": {"$arrayElemAt": ["$customer_details.name", 0]}},
                'customer_address': {"$first": {"$arrayElemAt": ["$customer_details.address", 0]}},
                'deliveryDate': {'$first': '$deliveryDate'},
                "products": {"$addToSet": {
                    "name": {"$arrayElemAt": ["$product_details.name", 0]}, 
                    "price": {"$ifNull": ["$products.custom_price", {"$arrayElemAt": ["$product_details.price", 0]}]},
                    "quantity": "$products.quantity"
                    }},
                "hampers": {"$addToSet": {
                    "name": {"$arrayElemAt": ["$hamper_details.name", 0]}, 
                    "price": {"$ifNull": ["$hampers.custom_price", {"$arrayElemAt": ["$hamper_details.price", 0]}]},
                    "quantity": "$hampers.quantity"}}
            }
        },
        {
            "$sort": {
                "deliveryDate": 1
            }
        }
    ]


# object creation
app = Flask(__name__)
database_key = os.environ["MONGOKEY"]
MCString = "mongodb+srv://salmonkarp:" + database_key + "@cookieskingdomdb.gq6eh6v.mongodb.net/"
print(MCString)
MClient = pymongo.MongoClient(MCString)['CK']
CORS(app)  # Enable CORS for all routes and origins

# Configure FLASK_DEBUG from environment variable
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG')

# menu
@app.route("/",methods=["GET"])
def root():
    return render_template('menu.html')

# add object get
@app.route("/add",methods=["GET"])
def add():
    ckProducts = MClient['Products']
    showIDProjection = {
        '_id':True,
        'name':True
    }
    productsList = list(ckProducts.find({},showIDProjection))
    return render_template("add_product.html",productsList=productsList)

# add object post
@app.route("/submit_addition",methods=["POST"])
def add_submit():
    product_type = request.form.get('product-type')
    try:
        if product_type == 'product':
            print('Product selected')
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
            return redirect('/')
        
        
        elif product_type == 'hampers':
            hamper_name = request.form.get('hname')
            selected_products = request.form.getlist('products[]')
            ckHampers = MClient['Hampers']
            hamper = {
                'name': hamper_name,
                'price': float(request.form.get('hprice')),
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

            # Insert the new hamper into the MongoDB database
            ckHampers.insert_one(hamper)
            return redirect('/')
    
    
    except Exception as e:
        return render_template('error.html',error=e)

# view object get
@app.route("/edit",methods=["GET"])
def edit_view():
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
                'price': 1,
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
                    'price': '$price'
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
                'price': '$_id.price',
                'items': 1
            }
        }
    ]

    hampersList = list(ckHampers.aggregate(pipeline))
    productsList = list(MClient['Products'].find())
    return render_template("edit_view.html", hampersList = hampersList, productsList = productsList)

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
    print(prices)
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
    return redirect('/')

# handle delete product get
@app.route("/delete_product/<productID>",methods=["GET"])
def delete_product(productID):
    ckConn = MClient['Products']
    ckConn.delete_many({
        '_id':ObjectId(productID)
    })
    return redirect('/')

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
        'price': float(request.form.get('hprice')),
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

    ckHampers.update_one({
        '_id': ObjectId(hampersID),
    },{
        '$set':hamper
    })
    return redirect('/')

@app.route("/delete_hampers/<hampersID>",methods=["GET"])
def delete_hampers(hampersID):
    ckHampers = MClient['Hampers']
    ckHampers.delete_many({
        '_id':ObjectId(hampersID)
    })
    return redirect('/')

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

    #adding products
    for product_id in selected_products:
        quantity_key = 'p_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        cutstom_price_key = product_id + "_custom_price"
        custom_price = request.form.get(cutstom_price_key, 0)
        if quantity > 0 and custom_price:
            OrderObject['products'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'custom_price':float(custom_price)
            })
        elif quantity > 0:
            OrderObject['products'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity,
            })

    #adding hampers
    for product_id in selected_hampers:
        quantity_key = 'h_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        cutstom_price_key = product_id + "_custom_price"
        custom_price = request.form.get(cutstom_price_key, 0)
        
        if quantity > 0 and custom_price:
            OrderObject['hampers'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'custom_price':float(custom_price)
            })
        elif quantity > 0:
            OrderObject['hampers'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity,
            })

    ckPOs = MClient['POs']
    ckPOs.insert_one(OrderObject)

    print(OrderObject)
    return redirect('/viewPOs')

@app.route("/viewPOs",methods=["GET","POST"])
def lookup():
    POData = MClient['POs']
    cust_pipeline = pipeline
    
    # handling specific date selection
    if request.method == "POST":
        view_type = request.form.get('viewType')

        if view_type == 'specificDate':
            specific_date = request.form.get('specificDate')
            # Filter orders based on specific date
            cust_pipeline = [{
                "$match": {
                    "deliveryDate": specific_date
                }
            }] + pipeline
        
        elif view_type == 'dateRange':
            start_date = request.form.get('startDate')
            end_date = request.form.get('endDate')
            # Filter orders based on date range
            cust_pipeline = [{
                "$match": {
                    "deliveryDate": {
                        "$gte": start_date,
                        "$lte": end_date
                    }
                }
            }] + pipeline
    
    # print(cust_pipeline)
    orders_data = list(POData.aggregate(cust_pipeline))
    print(len(orders_data))
    print(len(list(POData.find())))
    # pprint.PrettyPrinter(width=50).pprint(orders_data)    
    for order in orders_data:
        order_total = 0.0
        if order['products'] == [{}]:
            order['products'] = []
        if order['hampers'] == [{}]:
            order['hampers'] = []
        for product in order['products']:
            order_total += product['price'] * product['quantity']
        for product in order['hampers']:
            order_total += product['price'] * product['quantity']
        order['order_total'] = order_total
    return render_template('lookup.html',data = orders_data)

@app.route("/edit_po/<poID>",methods=["GET"])
def edit_po(poID):
    order_data = dict(MClient['POs'].find_one({'_id':ObjectId(poID)}))
    products_data = list(MClient['Products'].find())
    hampers_data = list(MClient['Hampers'].find())
    customer_data = dict(MClient['Customers'].find_one({'_id':order_data['custID']}))
    
    # Convert the list of products in order_data to a dictionary for easier lookup
    products_in_order = {str(product['product_id']): product for product in order_data.get('products', [])}
    hampers_in_order = {str(hamper['product_id']): hamper for hamper in order_data.get('hampers', [])}
    
    # Add a quantity and custom_price field to each product based on order_data
    for product in products_data:
        product_id_str = str(product['_id'])
        product_in_order = products_in_order.get(product_id_str, {})
        product['quantity_in_order'] = product_in_order.get('quantity', 0)
        product['custom_price_in_order'] = product_in_order.get('custom_price', product['price'])
        product['in_order'] = bool(product_in_order)  # Add in_order flag
        product['has_custom_price'] = 'custom_price' in product_in_order

    for hamper in hampers_data:
        hamper_id_str = str(hamper['_id'])
        hamper_in_order = hampers_in_order.get(hamper_id_str, {})
        hamper['quantity_in_order'] = hamper_in_order.get('quantity', 0)
        hamper['custom_price_in_order'] = hamper_in_order.get('custom_price', hamper['price'])
        hamper['in_order'] = bool(hamper_in_order)  # Add in_order flag
        hamper['has_custom_price'] = 'custom_price' in hamper_in_order
    
    # print(products_data)
    # print('haha',hampers_data)
    # pprint.PrettyPrinter(width=50).pprint(hampers_data)   
    return render_template("edit_po.html",order_data = order_data, products_data = products_data, hampers_data = hampers_data, customer_data = customer_data)

@app.route("/edit_po_submit",methods=["POST"])
def edit_po_submit():
    #handling customer
    custID = request.form.get('custID')
    customer_name = request.form.get('customer_name')
    customer_address = request.form.get('customer_address')
    print("stop",customer_name,customer_address)
    MClient['Customers'].update_one({'_id':ObjectId(custID)},{
        '$set':{
            'name':customer_name,
            'address':customer_address
        }
    })
    
    #handling delivery date
    orderID = request.form.get('orderID')
    deliveryDate = request.form.get('deliveryDate')
    
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
        cutstom_price_key = product_id + "_custom_price"
        custom_price = request.form.get(cutstom_price_key, 0)
        if quantity > 0 and custom_price:
            OrderObject['products'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'custom_price':float(custom_price)
            })
        elif quantity > 0:
            OrderObject['products'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity,
            })

    #adding hampers
    for product_id in selected_hampers:
        quantity_key = 'h_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        cutstom_price_key = product_id + "_custom_price"
        custom_price = request.form.get(cutstom_price_key, 0)
        
        if quantity > 0 and custom_price:
            OrderObject['hampers'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'custom_price':float(custom_price)
            })
        elif quantity > 0:
            OrderObject['hampers'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity,
            })

    ckPOs = MClient['POs']
    pprint.PrettyPrinter(width=50).pprint(OrderObject)   
    ckPOs.update_one({'_id':ObjectId(orderID)},{'$set':OrderObject})

    # print(OrderObject)
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