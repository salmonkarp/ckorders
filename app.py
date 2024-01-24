from flask import Flask, render_template, request, redirect, session, url_for, flash, get_flashed_messages
from dotenv import load_dotenv
from flask_cors import CORS
from bson.objectid import ObjectId
from datetime import datetime, timedelta, timezone
import pprint, os, pymongo, sqlite3
from babel.numbers import format_currency as fcrr
from babel.dates import format_date, format_datetime, format_time
from babel import Locale
import base64, math, os, requests
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Table, TableStyle, Paragraph

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
    startDate = datetime.strptime(target_dates[0],'%Y-%m-%d')
    endDate = datetime.strptime(target_dates[1],'%Y-%m-%d')
    return [order for order in orders if datetime.strptime(order['deliveryDate'],'%Y-%m-%d') >= startDate and datetime.strptime(order['deliveryDate'],'%Y-%m-%d') <= endDate]
def filter_orders_by_customer(orders,customerID):
    print(customerID)
    print(orders)
    return [order for order in orders if ObjectId(customerID) == order.get('custID',None)]
def calculate_order_total(po):
    order_total = 0.0
    for product in po['products'] + po['hampers']:
        price_value = product['price_value']
        quantity = product['quantity']
        discount_value = product['discount'] * product['price_value'] / 100.0
        item_subtotal = (price_value - discount_value) * quantity
        order_total += item_subtotal
    return order_total
def encode_pdf_as_base64(file_path):
    with open(file_path, 'rb') as pdf_file:
        pdf_content = pdf_file.read()
        encoded_content = base64.b64encode(pdf_content).decode('utf-8')
        return encoded_content
def send_whatsapp_message(po):
    message = "New Order!\n"
    message += "\n"
    message += "Customer Name: " + po['customer_name'] + '\n'
    message += "Customer Address: " + po['customer_address']  + '\n'
    message += "Delivery Date: " + po['deliveryDate'] + '\n'
    message += "\n"
    for item in po['products']:
        message += str(item['quantity']) + ' x ' + str(item['product_name']) + '\n'
    for item in po['hampers']:
        message += str(item['quantity']) + ' x ' + str(item['hamper_name']) + '\n'
    
    TELEGRAM_API_KEY = os.environ['TELEGRAM_API_KEY']
    base_url = f"https://api.telegram.org/bot{TELEGRAM_API_KEY}/sendMessage?chat_id=-4148902006&text={message}"
    requests.get(base_url)
    return
    


# objects creation
app = Flask(__name__)
app.secret_key = os.environ["SECRETKEY"]
database_key = os.environ["MONGOKEY"]
MCString = "mongodb+srv://salmonkarp:" + database_key + "@cookieskingdomdb.gq6eh6v.mongodb.net/"
MClient = pymongo.MongoClient(MCString)['CK']
app.jinja_env.filters['format_currency'] = format_currency
locale = Locale.parse('id_ID')
CORS(app)  # Enable CORS for all routes and origins

# Configure FLASK_DEBUG from environment variable
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG')

# Custom decorator for restricting access to certain routes
def restricted_access(role):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if 'username' not in session or 'role' not in session or session['role'] not in role:
                print('You do not have permission to access this page.', 'error')
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('login'))
            return func(*args, **kwargs)
        wrapper.__name__ = f'restricted_{role}_{func.__name__}'  # Unique function name
        return wrapper
    return decorator


##########################################################################
# Catch /
@app.route('/',methods=["GET"])
def catch_stray():
    print('test')
    return redirect('/login')

##########################################################################
# GROUP: HOME
# Admin home
@app.route("/dashboard",methods=["GET"])
@restricted_access(['admin'])
def root():
    return render_template('menu.html', user_type = session['role'])

# Orderuser home
@app.route("/dashboard_order",methods=["GET"])
@restricted_access(['orderUser','orderAdmin'])
def root_order():
    return render_template("menu.html", user_type = session['role'])

# Invoiceuser home
@app.route("/dashboard_invoice",methods=["GET"])
@restricted_access(['invoiceAdmin','invoiceUser'])
def root_invoice():
        return render_template("menu.html", user_type = session['role'])
# ENDGROUP: HOME

##########################################################################

## GROUP: MODIFY DETAILS
# modify details
@app.route("/modify",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def modify():
    return render_template("modify.html", user_type = session['role'])

# view product get
@app.route("/edit_product",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def edit_view_product():
    page = int(request.args.get('page', 1))
    start_index = (page - 1) * 10
    end_index = start_index + 10
    productsList = list(MClient['Products'].find().sort('name',pymongo.ASCENDING))
    total_pages = math.ceil(len(productsList) / 10.0)
    return render_template("edit_view_product.html", productsList = productsList[start_index:end_index], page=page, total_pages = total_pages, user_type = session['role'])

# view hamper get
@app.route("/edit_hamper",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def edit_view_hamper():
    page = int(request.args.get('page', 1))
    start_index = (page - 1) * 3
    end_index = start_index + 3
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
    total_pages = math.ceil(len(hampersList) / 3.0)
    return render_template("edit_view_hamper.html", hampersList = hampersList[start_index:end_index], page=page, total_pages=total_pages, user_type = session['role'])

# add product get
@app.route("/add_product",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def add_product():
    return render_template("add_product.html", user_type = session['role'])

# add hampers get
@app.route("/add_hampers",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def add_hampers():
    ckProducts = MClient['Products']
    showIDProjection = {
        '_id':True,
        'name':True
    }
    productsList = list(ckProducts.find({},showIDProjection).sort('name',pymongo.ASCENDING))
    return render_template("add_hampers.html",productsList=productsList, user_type = session['role'])

# add product post
@app.route("/submit_addition",methods=["POST"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
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
    os.environ["LAST_MODIFIED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return redirect('/edit_product')

# add hampers post
@app.route("/submit_addition_hampers",methods=["POST"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
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
    os.environ["LAST_MODIFIED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return redirect('/edit_hamper')

# edit product get
@app.route("/edit_product/<productID>",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def edit_product(productID):
    ckConn = MClient['Products']
    itemDetails = ckConn.find_one({
        '_id':ObjectId(productID)
    })
    return render_template('edit_product.html',product = itemDetails, user_type = session['role'])

# edit product post
@app.route("/edit_product_submit/<productID>", methods=["POST"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
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
    os.environ["LAST_MODIFIED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return redirect('/edit_product',)

# delete product get
@app.route("/delete_product/<productID>",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def delete_product(productID):
    ckConn = MClient['Products']
    ckConn.delete_many({
        '_id':ObjectId(productID)
    })
    os.environ["LAST_MODIFIED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return redirect('/edit_product')

# edit hampers get
@app.route("/edit_hampers/<hampersID>",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def edit_hampers(hampersID):
    productsList = list(MClient['Products'].find().sort('name',pymongo.ASCENDING))
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
        # print('added',item2['quantity'])
    # print(QuantDict)
    return render_template('edit_hampers.html',hamper = itemDetails, productsList = productsList, QuantDict = QuantDict, user_type = session['role'])

# edit hampers post
@app.route("/edit_hampers_submit/<hampersID>",methods=["POST"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
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
    os.environ["LAST_MODIFIED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return redirect('/edit_hamper')

# delete hampers post
@app.route("/delete_hampers/<hampersID>",methods=["GET"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def delete_hampers(hampersID):
    ckHampers = MClient['Hampers']
    ckHampers.delete_many({
        '_id':ObjectId(hampersID)
    })
    os.environ["LAST_MODIFIED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return redirect('/edit_hamper')

@app.route('/edit_view_customer',methods=['GET'])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def edit_view_customer():
    customers_data = list(MClient['Customers'].find())
    return render_template('edit_view_customer.html',data = customers_data, user_type = session['role'])

@app.route('/edit_customer/<custID>',methods=['GET'])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def edit_customer(custID):
    customer_data = dict(MClient['Customers'].find_one({'_id':ObjectId(custID)}))
    return render_template('edit_customer.html',data = customer_data, user_type = session['role'])

@app.route('/edit_customer_submit/<custID>',methods=['POST'])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def edit_customer_submit(custID):
    name = request.form.get('name')
    address = request.form.get('address')
    MClient['Customers'].update_many({'_id':ObjectId(custID)},{
        '$set':{
            'name':name,
            'address':address
        }
    })
    os.environ["LAST_MODIFIED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return redirect('/edit_view_customer')

@app.route('/delete_customer/<custID>',methods=["GET","POST"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def delete_customer(custID):
    MClient['Customers'].delete_many({'_id':ObjectId(custID)})
    os.environ["LAST_MODIFIED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return redirect('/edit_view_customer')

#ENDGROUP: MODIFY DETAILS

##########################################################################

#GROUP: PO
@app.route("/createPO",methods=['GET'])
@restricted_access(['admin','orderUser','orderAdmin'])
def createPO():
    customersList = list(MClient['Customers'].find())
    productsList = list(MClient['Products'].find()) 
    hampersList = list(MClient['Hampers'].find())
    current_date = datetime.now().strftime("%Y-%m-%d")
    # pnhList = products and hampers List
    return render_template('create_po.html',customersList = customersList, productsList = productsList, hampersList = hampersList, current_date = current_date, user_type = session['role'])

@app.route("/createPOSubmit",methods=["POST"])
@restricted_access(['admin','orderUser','orderAdmin'])
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
        quantity = request.form.get(quantity_key, 0)
        if quantity == '':
            quantity = 0
        else:
            quantity = int(quantity)
        discount_key = product_id + '_product_discount'
        discount = float(request.form.get(discount_key, 0))
        price_type = request.form.get(product_id + '_price_type', '')
        
        if quantity > 0:
            product_object = {
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'price_type': price_type
            }
        else:
            continue
        
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
        quantity = request.form.get(quantity_key, 0)
        if quantity == '':
            quantity = 0
        else:
            quantity = int(quantity)
        discount_key = product_id + '_hamper_discount'
        discount = float(request.form.get(discount_key, 0))
        price_type = request.form.get(product_id + '_price_type', '')
        
        if quantity > 0:
            hamper_entry = {
            'product_id': ObjectId(product_id),
            'quantity': quantity,
            'price_type': price_type
        }
        else:
            continue
            
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
    return redirect('/viewPOs')

@app.route("/viewPOs",methods=["GET","POST"])
@restricted_access(['admin','orderUser','orderAdmin'])
def lookup():
    page = int(request.args.get('page', 1))
    start_index = (page - 1) * 3
    end_index = start_index + 3
    
    orders_collection = MClient['POs']
    products_collection = MClient['Products']
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
            'custID': order['custID'],
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
    target_dates = []
    customerName = ""
    if request.method=='POST':
        if request.form.get('specificDate'):
            target_dates = [request.form.get('specificDate'),request.form.get('specificDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('startDate'):
            target_dates = [request.form.get('startDate'),request.form.get('endDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('viewType') == 'customer':
            filtered_orders = filter_orders_by_customer(result_sorted, request.form.get('customerID'))
            customerName = customers_collection.find_one({'_id':ObjectId(request.form.get('customerID',''))})['name']
            print(customerName)
        else:
            filtered_orders = result_sorted
    else:
        filtered_orders = result_sorted
    
    # pprint.PrettyPrinter(width=50).pprint(filtered_orders)
    print(len(filtered_orders))
    total_pages = math.ceil(len(filtered_orders) / 3.0)
    return render_template('lookup.html',data = filtered_orders[start_index:end_index], page=page, user_type = session['role'], total_pages = total_pages, target_dates = target_dates, customers_list = list(customers_collection.find()), customerName = customerName)

@app.route("/edit_po/<poID>",methods=["GET"])
@restricted_access(['admin','orderUser','orderAdmin'])
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

    return render_template("edit_po.html",order_data = order_data, products_data = products_data, hampers_data = hampers_data, customer_data = customer_data, customersList = customersList, user_type = session['role'])

@app.route("/edit_po_submit",methods=["POST"])
@restricted_access(['admin','orderUser','orderAdmin'])
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
        quantity = (request.form.get(quantity_key, 0))
        if quantity == '':
            quantity = 0
        else:
            quantity = int(quantity)
        discount_key = product_id + '_product_discount'
        discount = float(request.form.get(discount_key, 0))
        price_type = request.form.get(product_id + '_price_type', '')
        
        if quantity > 0:
            product_object = {
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'price_type': price_type
            }
        else:
            continue
        
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
        quantity = (request.form.get(quantity_key, 0))
        if quantity == '':
            quantity = 0
        else:
            quantity = int(quantity)
        discount_key = product_id + '_hamper_discount'
        discount = float(request.form.get(discount_key, 0))
        price_type = request.form.get(product_id + '_price_type', '')
        
        if quantity > 0:
            hamper_entry = {
            'product_id': ObjectId(product_id),
            'quantity': quantity,
            'price_type': price_type
        }
        else:
            continue
            
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
@restricted_access(['admin','orderUser','orderAdmin'])
def delete_po(poID):
    MClient['POs'].delete_many({
        '_id':ObjectId(poID)
    })
    return redirect('/viewPOs')

@app.route('/post_po/<poID>',methods=["GET","POST"])
@restricted_access(['admin','orderUser','orderAdmin'])
def post_po(poID):
    if request.method == 'GET':
        return render_template('post_po_confirm.html',poID = poID, user_type = session['role'])
    else:
        order = dict(MClient['POs'].find_one({'_id':ObjectId(poID)}))
        customers_collection = MClient['Customers']
        products_collection = MClient['Products']
        hampers_collection = MClient['Hampers']
        
        customer = customers_collection.find_one({'_id': order['custID']})
        products_data = []

        for product in order.get('products', []):
            product_doc = products_collection.find_one({'_id': product['product_id']})
            price_type = product.get('price_type', 'custom')
            price_value = product['custom_price'] if price_type == 'custom' else next(
                (price['value'] for price in product_doc['prices'] if price['name'] == price_type), None
            )
            discount = product.get('discount', 0.0)
            quantity = product.get('quantity')
            append_object = {
                '_id': product['product_id'],
                'product_name': product_doc['name'],
                'quantity': quantity,
                'price_type':price_type,
                'price_value':price_value,
            }
            if discount > 0.0:
                append_object['discount'] = discount
            else:
                append_object['discount'] = 0.0
            
            products_data.append(append_object)

        hampers_data = []

        for hamper in order.get('hampers', []):
            hamper_doc = hampers_collection.find_one({'_id': hamper['product_id']})
            price_type = hamper.get('price_type', 'custom')
            price_value = hamper['custom_price'] if price_type == 'custom' else next(
                (price['value'] for price in hamper_doc['prices'] if price['name'] == price_type), None
            )
            discount = hamper.get('discount', 0.0)
            quantity = hamper.get('quantity')
            append_object = {
                '_id': hamper['product_id'],
                'hamper_name': hamper_doc['name'],
                'quantity': hamper.get('quantity'),
                'price_type':price_type,
                'price_value':price_value,
            }
            if discount > 0.0:
                append_object['discount'] = discount
            else:
                append_object['discount'] = 0.0
            
            for product in hamper_doc['items']:
                print(product)
                product_doc = products_collection.find_one({'_id': product['product_id']})
            hampers_data.append(append_object)
        
        archived_object = {
            '_id': ObjectId(poID),
            'custID':customer['_id'],
            'customer_name': customer['name'],
            'customer_address': customer['address'],
            'deliveryDate': order['deliveryDate'],
            'products': products_data,
            'hampers': hampers_data,
            'orderDiscount': order.get('orderDiscount', 0.0),
            'postedTime':datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        MClient['PostedPOs'].insert_one(archived_object)
        MClient['POs'].delete_many({'_id':ObjectId(poID)})
        send_whatsapp_message(archived_object)
        return redirect('/viewPosted')

@app.route("/viewPosted",methods=["GET","POST"])
@restricted_access(['admin','orderUser','orderAdmin'])
def lookup_posted():
    page = int(request.args.get('page', 1))
    start_index = (page - 1) * 3
    end_index = start_index + 3
    customers_collection = MClient['Customers']
    
    result = list(MClient['PostedPOs'].find())
    for order in result:
        order['order_total'] = calculate_order_total(order)
    result_sorted = sorted(result, key=lambda x: datetime.strptime(x['deliveryDate'], '%Y-%m-%d'))
    
    # for specific date handling
    target_dates = []
    customerName = ""
    if request.method=='POST':
        if request.form.get('specificDate'):
            target_dates = [request.form.get('specificDate'),request.form.get('specificDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('startDate'):
            target_dates = [request.form.get('startDate'),request.form.get('endDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('viewType') == 'customer':
                filtered_orders = filter_orders_by_customer(result_sorted, request.form.get('customerID'))
                customerName = customers_collection.find_one({'_id':ObjectId(request.form.get('customerID',''))})['name']
                print(customerName)
        else:
            filtered_orders = result_sorted
    else:
        filtered_orders = result_sorted
    
    total_pages = math.ceil(len(filtered_orders)/3.0)
    # pprint.PrettyPrinter(width=50).pprint(filtered_orders)
    return render_template('posted_view.html',data = filtered_orders[start_index:end_index], page=page, user_type = session['role'], target_dates = target_dates, total_pages = total_pages, customers_list = list(customers_collection.find()), customerName = customerName)


#ENDGROUP

###################################################################

#GROUP: INVOICE
@app.route('/createInvoice',methods=["GET","POST"])
@restricted_access(['admin','invoiceUser','invoiceAdmin'])
def create_invoice():
    # first page, choose between new or take from posted
    if request.method == 'GET':
        return render_template('create_invoice_start.html', user_type = session['role'])
    
    # create from scratch
    elif request.form.get('create-type') == 'new':
        #copy from create PO
        customersList = list(MClient['Customers'].find())
        productsList = list(MClient['Products'].find()) 
        hampersList = list(MClient['Hampers'].find())
        current_date = datetime.now().strftime("%Y-%m-%d")
        return render_template('create_invoice_new.html', customersList = customersList, productsList = productsList, hampersList = hampersList, current_date = current_date, user_type = session['role'])
    
    # take from posted
    else:
        #copy from view posted
        customers_collection = MClient['Customers']
        page = int(request.args.get('page', 1))
        start_index = (page - 1) * 3
        end_index = start_index + 3
        
        result = list(MClient['PostedPOs'].find({
            '$or':[
                {'wasConverted':False},
                {'wasConverted':{'$exists':False}}
            ]
            
            }))
        for order in result:
            order['order_total'] = calculate_order_total(order)
        result_sorted = sorted(result, key=lambda x: datetime.strptime(x['deliveryDate'], '%Y-%m-%d'))
        
        # for specific date handling
        target_dates = []
        customerName = ""
        if request.method=='POST':
            if request.form.get('specificDate'):
                target_dates = [request.form.get('specificDate'),request.form.get('specificDate')]
                filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
            elif request.form.get('startDate'):
                target_dates = [request.form.get('startDate'),request.form.get('endDate')]
                filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
            elif request.form.get('viewType') == 'customer':
                filtered_orders = filter_orders_by_customer(result_sorted, request.form.get('customerID'))
                customerName = customers_collection.find_one({'_id':ObjectId(request.form.get('customerID',''))})['name']
                print(customerName)
            else:
                filtered_orders = result_sorted
        else:
            filtered_orders = result_sorted
        
        total_pages = math.ceil(len(filtered_orders)/3.0)
        # pprint.PrettyPrinter(width=50).pprint(filtered_orders)
        return render_template('posted_view_invoice.html',data = filtered_orders[start_index:end_index], page=page, user_type = session['role'], target_dates = target_dates, total_pages = total_pages, customers_list = list(customers_collection.find()), customerName = customerName)

def convert_from_old(order_details):
    try:
        products_updated, hampers_updated = [], []
        customers_collection = MClient['Customers']
        products_collection = MClient['Products']
        hampers_collection = MClient['Hampers']
        # print('test_top')
        #check customer data
        real_customer_data = dict(customers_collection.find_one({'_id':order_details['custID']}))
        # print(real_customer_data)
        if real_customer_data['name'] != order_details['customer_name']:
            raise ValueError('name')
        elif real_customer_data['address'] != order_details['customer_address']:
            raise ValueError('address')
        
        #check products
        for product in order_details['products']:
            # print(product)
            real_product_data = dict(products_collection.find_one({'_id':product['_id']}))
            # print(real_product_data)
            if real_product_data['name'] != product['product_name']:
                raise ValueError('product name')
            
            # print('cust true2')
            product_prices_dict = {}
            for price in real_product_data['prices']:
                product_prices_dict[price['name']] = price['value']
            
            if product['price_type'] not in product_prices_dict.keys():
                raise ValueError('price_type not exist')
            if product_prices_dict[product['price_type']] != product['price_value']:
                raise ValueError('price type/value mismatch')
            
            products_updated.append({
                'product_id':real_product_data['_id'],
                'quantity':product['quantity'],
                'price_type':product['price_type'],
                'discount':product.get('discount',0.0)
            })
        
        #check hampers
        for product in order_details['hampers']:
            real_product_data = dict(hampers_collection.find_one({'_id':product['_id']}))
            if real_product_data['name'] != product['hamper_name']:
                raise ValueError('hamper name')
            
            product_prices_dict = {}
            for price in real_product_data['prices']:
                product_prices_dict[price['name']] = price['value']
            
            if product['price_type'] not in product_prices_dict.keys():
                raise ValueError('price_type not exist')
            if product_prices_dict[product['price_type']] != product['price_value']:
                raise ValueError('price type/value mismatch')
            
            hampers_updated.append({
                'product_id':real_product_data['_id'],
                'quantity':product['quantity'],
                'price_type':product['price_type'],
                'discount':product.get('discount',0.0)
            })
        
        invoice_object = {
            'po_id':order_details['_id'],
            'custID':order_details['custID'],
            'deliveryDate':order_details['deliveryDate'],
            'products':products_updated,
            'hampers':hampers_updated,
            'orderDiscount':order_details['orderDiscount'],
            'invoiceType':'updated'
        }
        
        return invoice_object
    except Exception as e:
        return e

def convert_from_new(order_details):
    products_updated, hampers_updated = [], []
    
    #check products
    for product in order_details['products'] + order_details['hampers']:
        products_updated.append({
            'product_id':product['_id'],
            'quantity':product['quantity'],
            'price_type':product['price_type'],
            'discount':product.get('discount',0.0)
        })
    
    invoice_object = {
        'po_id':order_details['_id'],
        'custID':order_details['custID'],
        'deliveryDate':order_details['deliveryDate'],
        'products':products_updated,
        'hampers':hampers_updated,
        'orderDiscount':order_details['orderDiscount'],
        'invoiceType':'updated'
    }
    
    return invoice_object

@app.route('/createInvoiceFromPosted/<postedID>',methods=["GET"])
@restricted_access(['admin','invoiceUser','invoiceAdmin'])
def create_invoice_from_posted(postedID):
    #tries to convert posted into an invoice, if not tries to fix
    
    lastModifiedTime = datetime.strptime(os.environ['LAST_MODIFIED'],"%Y-%m-%d %H:%M:%S")
    order_details = dict(MClient["PostedPOs"].find_one({'_id':ObjectId(postedID)}))
    order_posted_time  = datetime.strptime(order_details['postedTime'], "%Y-%m-%d %H:%M:%S")
    print(order_details)
    
    # if order is made before last change
    if order_posted_time < lastModifiedTime:
        try:
            invoice_object = convert_from_old(order_details)
            print("result:",invoice_object)
            
            # any failure in conversion, raise error
            if type(invoice_object) != dict:
                raise ValueError(invoice_object)

            # successful conversion, then insert to invoices
            MClient['Invoices'].insert_one(invoice_object)
            invoiceID = dict(MClient['Invoices'].find_one({'po_id':ObjectId(postedID)}))['_id']
            MClient['PostedPOs'].update_one({'_id':ObjectId(postedID)},{
                '$set':{
                    'wasConverted':True
                }
            })
            return redirect(f'/print_invoice/{invoiceID}')
            
        # handling of failed conversion -> use manual input
        except Exception as e:
            print(e)
            MClient['PostedPOs'].update_one({'_id':ObjectId(postedID)},{
                '$set':{
                    'wasConverted':True
                }
            })
            return render_template('create_invoice_manual.html',data=order_details, error=e, user_type = session['role'])
    else:
        invoice_object = convert_from_new(order_details)
        MClient['Invoices'].insert_one(invoice_object)
        invoiceID = dict(MClient['Invoices'].find_one({'po_id':ObjectId(postedID)}))['_id']
        return redirect(f"/print_invoice/{invoiceID}")

@app.route('/insertInvoice',methods=['POST'])
@restricted_access(['admin','invoiceUser','invoiceAdmin'])
def insert_invoice():
    #only handle invoices from scratch OR broken ones
    #handle like new order
    if request.form.get('invoiceType') == 'new':
        
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
            'hampers':[],
            'invoiceType':'new'
        }

        if orderDiscount > 0:
            OrderObject['orderDiscount']=orderDiscount
        else:
            OrderObject['orderDiscount'] = 0.0
        
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
        invoiceID = MClient['Invoices'].insert_one(OrderObject).inserted_id
        # print(OrderObject)
        return redirect(f'/print_invoice/{invoiceID}')
    
    #convert data to all custom
    else:
        order_object = {
            'customer_name':request.form.get('customer_name'),
            'customer_address':request.form.get('customer_address'),
            'deliveryDate':request.form.get('deliveryDate'),
            'orderDiscount':float(request.form.get('orderDiscount')),
            'items':[],
            'invoiceType':'broken',
        }
        product_name_array = request.form.getlist('product_name[]')
        product_price_array = request.form.getlist('product_price[]')
        quantity_array = request.form.getlist('quantity[]')
        discount_array = request.form.getlist('discount[]')
        print(product_name_array, product_price_array, quantity_array, discount_array)
        for i in range(len(product_name_array)):
            try:
                a,b,c,d = product_name_array[i], product_price_array[i], quantity_array[i], discount_array[i]
            except:
                continue
            order_object['items'].append({
                'name':product_name_array[i],
                'price_value':float(product_price_array[i]),
                'quantity':int(quantity_array[i]),
                'discount':float(discount_array[i]),
                
            })
        invoiceID = MClient['Invoices'].insert_one(order_object).inserted_id
        return redirect(f'/print_invoice/{invoiceID}')

@app.route('/viewInvoices',methods=['GET','POST'])
@restricted_access(['admin','invoiceUser','invoiceAdmin'])
def view_invoices():
    page = int(request.args.get('page', 1))
    start_index = (page - 1) * 3
    end_index = start_index + 3
    
    orders_collection = MClient['Invoices']
    products_collection = MClient['Products']
    hampers_collection = MClient['Hampers']
    customers_collection = MClient['Customers']
    
    result = []

    for order in orders_collection.find():
        if order['invoiceType'] != 'broken':
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
                'custID' : order.get('custID',None),
                'customer_name': customer['name'],
                'customer_address': customer['address'],
                'deliveryDate': order['deliveryDate'],
                'products': products_data,
                'hampers': hampers_data,
                'orderDiscount': order.get('orderDiscount', 0.0)
            })
        else:
            for product in order['items']:
                product['product_name'] = product['name']
                product['price_name'] = 'custom'
            result.append({
                '_id': order['_id'],
                'customer_name': order['customer_name'],
                'customer_address': order['customer_address'],
                'deliveryDate': order['deliveryDate'],
                'products': order['items'],
                'hampers': [],
                'orderDiscount': order.get('orderDiscount', 0.0)
            })

    # calculating order total :/
    for order in result:
        order['order_total'] = calculate_order_total(order)
    result_sorted = sorted(result, key=lambda x: datetime.strptime(x['deliveryDate'], '%Y-%m-%d'))
    
    # for specific date handling
    target_dates = []
    customerName = ""
    if request.method=='POST':
        if request.form.get('specificDate'):
            target_dates = [request.form.get('specificDate'),request.form.get('specificDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('startDate'):
            target_dates = [request.form.get('startDate'),request.form.get('endDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('viewType') == 'customer':
            filtered_orders = filter_orders_by_customer(result_sorted, request.form.get('customerID'))
            customerName = customers_collection.find_one({'_id':ObjectId(request.form.get('customerID',''))})['name']
            print(customerName)
        else:
            filtered_orders = result_sorted
    else:
        filtered_orders = result_sorted
    
    # pprint.PrettyPrinter(width=50).pprint(filtered_orders)
    print(len(filtered_orders))
    total_pages = math.ceil(len(filtered_orders) / 3.0)
    return render_template('lookup_invoices.html',data = filtered_orders[start_index:end_index], page=page, user_type = session['role'], total_pages = total_pages, target_dates = target_dates, customers_list = list(customers_collection.find()), customerName = customerName)

@app.route('/archive_invoice/<invoiceID>',methods=['GET','POST'])
@restricted_access(['admin','orderAdmin'])
def archive_invoice(invoiceID):
    if request.method == 'GET':
        return render_template('archive_invoice_confirm.html', data=invoiceID, user_type = session['role'], poID = invoiceID)
    
    order = dict(MClient['Invoices'].find_one({'_id':ObjectId(invoiceID)}))
    if order['invoiceType'] != 'broken':
        poID = invoiceID
        customers_collection = MClient['Customers']
        products_collection = MClient['Products']
        hampers_collection = MClient['Hampers']
        
        customer = customers_collection.find_one({'_id': order['custID']})
        products_data = []

        for product in order.get('products', []):
            product_doc = products_collection.find_one({'_id': product['product_id']})
            price_type = product.get('price_type', 'custom')
            price_value = product['custom_price'] if price_type == 'custom' else next(
                (price['value'] for price in product_doc['prices'] if price['name'] == price_type), None
            )
            discount = product.get('discount', 0.0)
            quantity = product.get('quantity')
            currentStock = product_doc.get('currentStock',0)
            
            append_object = {
                '_id': product['product_id'],
                'product_name': product_doc['name'],
                'quantity': quantity,
                'price_type':price_type,
                'price_value':price_value,
            }
            if discount > 0.0:
                append_object['discount'] = discount
            else:
                append_object['discount'] = 0.0
            
            if currentStock - quantity < 0:
                newStock = 0
            else:
                newStock = currentStock - quantity
            products_collection.update_one({'_id': product['product_id']}, {
                '$set':{
                    'currentStock':newStock
                }
            })
            products_data.append(append_object)

        hampers_data = []

        for hamper in order.get('hampers', []):
            hamper_doc = hampers_collection.find_one({'_id': hamper['product_id']})
            price_type = hamper.get('price_type', 'custom')
            price_value = hamper['custom_price'] if price_type == 'custom' else next(
                (price['value'] for price in hamper_doc['prices'] if price['name'] == price_type), None
            )
            discount = hamper.get('discount', 0.0)
            quantity = hamper.get('quantity')
            append_object = {
                '_id': hamper['product_id'],
                'hamper_name': hamper_doc['name'],
                'quantity': hamper.get('quantity'),
                'price_type':price_type,
                'price_value':price_value,
            }
            if discount > 0.0:
                append_object['discount'] = discount
            else:
                append_object['discount'] = 0.0
            
            for product in hamper_doc['items']:
                print(product)
                product_doc = products_collection.find_one({'_id': product['product_id']})
                currentStock = product_doc.get('currentStock',0)
                if currentStock - (quantity * product['quantity']) < 0:
                        newStock = 0
                else:
                    newStock = currentStock - (quantity * product['quantity'])
                products_collection.update_one({'_id': product['product_id']}, {
                    '$set':{
                        'currentStock':newStock
                    }
                })
            hampers_data.append(append_object)
        
        archived_object = {
            '_id': ObjectId(poID),
            'custID':customer['_id'],
            'customer_name': customer['name'],
            'customer_address': customer['address'],
            'deliveryDate': order['deliveryDate'],
            'products': products_data,
            'hampers': hampers_data,
            'orderDiscount': order.get('orderDiscount', 0.0),
            'archivedTime':datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'invoiceType':order['invoiceType']
        }
        
        MClient['ArchivedInvoices'].insert_one(archived_object)
        MClient['Invoices'].delete_many({'_id':ObjectId(poID)})
        return redirect('/viewArchived')
    else:
        MClient['ArchivedInvoices'].insert_one(order)
        MClient['Invoices'].delete_many({'_id':ObjectId(invoiceID)})
        return redirect('/viewArchived')
    
@app.route('/viewArchived', methods=['GET','POST'])
@restricted_access(['admin','invoiceAdmin', 'orderAdmin'])
def view_archived():
    page = int(request.args.get('page', 1))
    start_index = (page - 1) * 3
    end_index = start_index + 3
    customers_collection = MClient['Customers']
    
    result = list(MClient['ArchivedInvoices'].find())
    for order in result:
        if order['invoiceType'] == 'broken':
            order['products'] = order['items']
            order['hampers'] = []
            for item in order['products']:
                item['product_name'] = item['name']
                item['price_type'] = 'custom'
        order['order_total'] = calculate_order_total(order)
    result_sorted = sorted(result, key=lambda x: datetime.strptime(x['deliveryDate'], '%Y-%m-%d'))
    
    # for specific date handling
    target_dates = []
    customerName = ""
    if request.method=='POST':
        if request.form.get('specificDate'):
            target_dates = [request.form.get('specificDate'),request.form.get('specificDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('startDate'):
            target_dates = [request.form.get('startDate'),request.form.get('endDate')]
            filtered_orders = filter_orders_by_dates(result_sorted, target_dates)
        elif request.form.get('viewType') == 'customer':
            filtered_orders = filter_orders_by_customer(result_sorted, request.form.get('customerID'))
            customerName = customers_collection.find_one({'_id':ObjectId(request.form.get('customerID',''))})['name']
            print(customerName)
        else:
            filtered_orders = result_sorted
    else:
        filtered_orders = result_sorted
    
    total_pages = math.ceil(len(filtered_orders)/3.0)
    # pprint.PrettyPrinter(width=50).pprint(filtered_orders)
    return render_template('archived_view_invoice.html',data = filtered_orders[start_index:end_index], page=page, user_type = session['role'], target_dates = target_dates, total_pages = total_pages, customers_list = list(customers_collection.find()), customerName = customerName)

@app.route('/print_invoice/<invoiceID>',methods=['GET'])
@restricted_access(['admin','invoiceAdmin','invoiceUser'])
def print_invoice(invoiceID):
    order = dict(MClient['Invoices'].find_one({'_id':ObjectId(invoiceID)}))
    if order['invoiceType'] != 'broken':
        products_collection = MClient['Products']
        hampers_collection = MClient['Hampers']
        customers_collection = MClient['Customers']
        
        customer = customers_collection.find_one({'_id': order['custID']})
        products_data = []

        for product in order.get('products', []):
            product_doc = products_collection.find_one({'_id': product['product_id']})
            price_type = product.get('price_type', 'custom')
            price_value = product['custom_price'] if price_type == 'custom' else next(
                (price['value'] for price in product_doc['prices'] if price['name'] == price_type), None
            )
            products_data.append({
                'name': product_doc['name'],
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
                'name': hamper_doc['name'],
                'price_name': price_type,
                'price_value': price_value,
                'quantity': hamper.get('quantity'),
                'discount': hamper.get('discount', 0.0)
            })

        result = {
            '_id': order['_id'],
            'customer_name': customer['name'],
            'customer_address': customer['address'],
            'deliveryDate': order['deliveryDate'],
            'products': products_data,
            'hampers': hampers_data,
            'orderDiscount': order.get('orderDiscount', 0.0)
        }
    else:
        result = {
            '_id': order['_id'],
            'customer_name': order['customer_name'],
            'customer_address': order['customer_address'],
            'deliveryDate': order['deliveryDate'],
            'products': order['items'],
            'hampers': [],
            'orderDiscount': order.get('orderDiscount', 0.0)
        }
    
    output_directory = 'pdf_results'
    os.makedirs(output_directory, exist_ok=True)
    output_pdf_path = os.path.join('pdf_results', 'output.pdf')
    
    page_height_cm = 21.3 * cm
    page_size = (16.2 * cm, 21.3 * cm)
    pdf = canvas.Canvas(output_pdf_path, pagesize=page_size)
    # pdf = SimpleDocTemplate(output_pdf_path, pagesize=page_size)
    content = []
    labels = []
    order_total = 0.0
    
    #handling customer
    dateObject = datetime.strptime(result['deliveryDate'],"%Y-%m-%d")
    formatted_date = format_date(dateObject, locale='id_ID')
    labels.append((formatted_date, (13.5 * cm, page_height_cm - 1.5 * cm)))
    labels.append((result['customer_name'], (12.8 * cm, page_height_cm - 2.7 * cm)))
    custAdd = result['customer_address']
    def split_address(address):
        # Check if the address is already short enough
        if len(address) <= 14:
            return address, ""

        # Find a space near the middle of the address
        mid_index = len(address) // 2
        while mid_index < len(address) and address[mid_index] != ' ':
            mid_index += 1

        # If no space is found, split at the middle
        if mid_index == len(address):
            mid_index = len(address) // 2

        # Split the address at the found space or middle
        first_part = address[:mid_index].rstrip()
        second_part = address[mid_index:].lstrip()

        return first_part, second_part
    
    if custAdd or custAdd == 'None':
        part1, part2 = split_address(custAdd)
    else:
        part1, part2 = "", ""
        
    labels.append((part1, (12.8 * cm, page_height_cm - 3.4 * cm)))
    labels.append((part2, (12.8 * cm, page_height_cm - 4.1 * cm)))
    
    for text, (x, y) in labels:
        tempPara = Paragraph(text,style=getSampleStyleSheet()['BodyText'])
        tempPara.wrapOn(pdf,300,300)
        tempPara.drawOn(pdf,x,y)
        # pdf.drawString(x,y,text)
        
    table_data = []
    item_counter = 0
    for product in result['products'] + result['hampers']:
        current_row_data= []
        current_row_data.append(f"{product['quantity']} pcs")
        current_row_data.append(f"{product['name']}")
        
        price_value = product['price_value']
        if 'price_name' in product.keys():
            price_name = product['price_name']
        else:
            price_name = 'custom'
        quantity = product['quantity']
        current_row_data.append(f"{int(price_value)} ({price_name[0]})")
        
        if product['discount'] > 0.0:
            discount = product['discount']
            discount_value = round(discount * 0.01 * price_value / 100) * 100
            final_value = int(price_value - discount_value)
            
            discount_row_data = ["",f"Discount ({discount}%)",f"-{discount_value}", ""]
            final_value_data = ["","",f"  ={final_value}",""]
            current_row_data.append(int(final_value * quantity))
            order_total += final_value * quantity
            table_data.append(current_row_data)
            table_data.append(discount_row_data)
            table_data.append(final_value_data)
            item_counter += 3
        else:
            total_value = int(price_value * quantity)
            current_row_data.append(total_value)
            order_total += total_value
            table_data.append(current_row_data)
            item_counter += 1
    
    print(table_data)
    if result['orderDiscount'] > 0.0:
        rows_to_append = 13 - item_counter
        for i in range(rows_to_append): table_data.append(["","","",""])
        table_data.append(["","Subtotal","",f"{round(order_total/100)*100}"])
        discount_value = round(result['orderDiscount'] * 0.01 * order_total / 100) * 100
        table_data.append(["",f"Order Discount ({round(result['orderDiscount'])}%)","",f"-{discount_value}"])
        final_value = round((order_total - discount_value) / 100) * 100
        table_data.append(["","","",f"{final_value}"])
    else:
        rows_to_append = 15 - item_counter
        for i in range(rows_to_append): table_data.append(["","","",""])
        table_data.append(["","","",f"{round(order_total/100)*100}"])
    
    
    col_widths_cm = [2.2 * cm, 6.8 * cm, 2.4 * cm, 2.8 * cm]
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),  # White background for the header row
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),  # Text color for the header row
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white), # White background for data rows
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),       # Arial font for data rows
    ])
    print(table_data)
    table = Table(table_data, colWidths=col_widths_cm)
    table.setStyle(table_style)
    table_x = 2 * cm
    table_y = 4 * cm
    table_position = (table_x, page_size[1] - table_y)
    print(table_position)
    table.leftIndent = table_x
    table.topIndent = page_size[1] - table_y
    
    # pdf.line(0,0,100,100)
    table.wrapOn(pdf,0,0)
    table.drawOn(pdf,table_x,table_y)
    pdf.showPage()
    pdf.save()
    
    print(output_pdf_path)
    encoded_pdf_content = encode_pdf_as_base64(output_pdf_path)
    return render_template('print_invoice.html',encoded_content = encoded_pdf_content, user_type = session['role'], invoiceID = invoiceID)

@app.route('/edit_invoice/<poID>',methods=['GET'])
@restricted_access(['admin','invoiceAdmin','invoiceUser'])
def edit_invoice(poID):
    order_data = dict(MClient['Invoices'].find_one({'_id':ObjectId(poID)}))
    if order_data['invoiceType'] != 'broken':
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

        return render_template("edit_invoice.html",order_data = order_data, products_data = products_data, hampers_data = hampers_data, customer_data = customer_data, customersList = customersList, user_type = session['role'])
    else:
        return render_template("edit_invoice_manual.html",data = order_data, user_type = session['role'])

@app.route('/edit_invoice_submit',methods=['POST'])
@restricted_access(['admin','invoiceAdmin','invoiceUser'])
def edit_invoice_submit():
    poID = request.form.get('invoiceID')
    order_data = dict(MClient['Invoices'].find_one({'_id':ObjectId(poID)}))
    if order_data['invoiceType'] != 'broken':
        orderID = poID
        
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
            quantity = (request.form.get(quantity_key, 0))
            if quantity == '':
                quantity = 0
            else:
                quantity = int(quantity)
            discount_key = product_id + '_product_discount'
            discount = float(request.form.get(discount_key, 0))
            price_type = request.form.get(product_id + '_price_type', '')
            
            if quantity > 0:
                product_object = {
                    'product_id': ObjectId(product_id),
                    'quantity': quantity,
                    'price_type': price_type
                }
            else:
                continue
            
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
            quantity = (request.form.get(quantity_key, 0))
            if quantity == '':
                quantity = 0
            else:
                quantity = int(quantity)
            discount_key = product_id + '_hamper_discount'
            discount = float(request.form.get(discount_key, 0))
            price_type = request.form.get(product_id + '_price_type', '')
            
            if quantity > 0:
                hamper_entry = {
                'product_id': ObjectId(product_id),
                'quantity': quantity,
                'price_type': price_type
            }
            else:
                continue
                
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
        ckPOs = MClient['Invoices']
        pprint.PrettyPrinter(width=50).pprint(OrderObject)   
        ckPOs.update_one({'_id':ObjectId(poID)},{'$set':OrderObject})

        print(OrderObject)
        return redirect(f'/print_invoice/{poID}')
    else:
        order_object = {
            'customer_name':request.form.get('customer_name'),
            'customer_address':request.form.get('customer_address'),
            'deliveryDate':request.form.get('deliveryDate'),
            'orderDiscount':float(request.form.get('orderDiscount')),
            'items':[],
            'invoiceType':'broken',
        }
        product_name_array = request.form.getlist('product_name[]')
        product_price_array = request.form.getlist('product_price[]')
        quantity_array = request.form.getlist('quantity[]')
        discount_array = request.form.getlist('discount[]')
        for i in range(len(product_name_array)):
            try:
                a,b,c,d = product_name_array[i], product_price_array[i], quantity_array[i], discount_array[i]
            except:
                continue
            order_object['items'].append({
                'name':product_name_array[i],
                'price_value':float(product_price_array[i]),
                'quantity':int(quantity_array[i]),
                'discount':float(discount_array[i]),
                
            })
        MClient['Invoices'].update_many({'_id':ObjectId(poID)},{'$set':order_object})
        return redirect(f'/print_invoice/{poID}')
      
@app.route('/delete_invoice/<invoiceID>',methods=['GET'])
@restricted_access(['admin','invoiceAdmin','invoiceUser'])
def delete_invoice(invoiceID):
    MClient['Invoices'].delete_one({'_id':ObjectId(invoiceID)})
    return redirect('/viewInvoices')

#ENDGROUP

###################################################################

#GROUP: SUMMARY
@app.route('/summary',methods=["GET","POST"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def summary():
    if request.method == "GET":
        return render_template('summary.html', user_type = session['role'])
    else:
        startDate = request.form.get('startDate')
        endDate = request.form.get('endDate')
        CustomersData = MClient['Customers']
        ProductsDataRaw = MClient['Products']
        HampersData = MClient['Hampers']
        
        # sorting by products, combined with hampers
        if request.form.get('viewType') == 'productSortCombined':
            OrderData = MClient['ArchivedInvoices'].find(
                {
                    'deliveryDate':{
                        '$gte':startDate,
                        '$lte':endDate
                    }
                }
            )
            ProductsData = ProductsDataRaw.find()
            product_totals = {}
            customers_list = []
            broken_orders = []
            order_count = 0
            for order in OrderData:
                order_count += 1
                if order['invoiceType'] == 'broken':
                    broken_orders.append(order)
                    continue
                customer_data = dict(CustomersData.find_one({'_id':order['custID']}))
                if customer_data['name'] not in customers_list:
                    customers_list.append(customer_data['name'])
                for product in order.get('products',[]):
                    product_id = str(product['_id'])
                    quantity = product['quantity']
                    product_totals[product_id] = product_totals.get(product_id, 0) + quantity
                for hamper in order.get('hampers',[]):
                    hamper_id = str(hamper['_id'])
                    hamper_quantity = hamper['quantity']
                    hamper_details = HampersData.find_one({'_id':ObjectId(hamper_id)})
                    
                    if hamper_details:
                        hamper_products = hamper_details['items']
                    else:
                        hamper_products = []
                        
                    # print(hamper_products)
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
                        'total_quantity':total_quantity,
                        'current_stock':product['currentStock']
                    }
                )
            
            additional_details = {
                "order_count" : order_count,
                "customers_list":customers_list,
                "broken_orders":broken_orders
            }
            return render_template('summary_product.html',data=summary_data, startDate = startDate, endDate = endDate, additional_details = additional_details, user_type = session['role'])
        
        # sorting by products, separate from hampers
        elif request.form.get('viewType') == 'productSort':
            OrderData = MClient['ArchivedInvoices'].find(
                {
                    'deliveryDate':{
                        '$gte':startDate,
                        '$lte':endDate
                    }
                }
            )
            ProductsData = ProductsDataRaw.find()
            product_totals = {}
            customers_list = []
            order_count = 0
            broken_orders = []
            for order in OrderData:
                order_count += 1
                if order['invoiceType'] == 'broken':
                    broken_orders.append(order)
                    continue
                customer_data = dict(CustomersData.find_one({'_id':order['custID']}))
                if customer_data['name'] not in customers_list:
                    customers_list.append(customer_data['name'])
                
                for product in order.get('products',[]):
                    product_id = str(product['_id'])
                    quantity = product['quantity']
                    product_totals[product_id] = product_totals.get(product_id, 0) + quantity
                
                for hamper in order.get('hampers',[]):
                    hamper_id = str(hamper['_id'])
                    hamper_quantity = hamper['quantity']
                    product_totals[hamper_id] = product_totals.get(hamper_id, 0) + hamper_quantity
                        
            print(product_totals)
            summary_data = []
            for product in list(ProductsData) + list(HampersData.find()):
                product_id = str(product['_id'])
                product_name = product['name']
                total_quantity = product_totals.get(product_id,0)
                if total_quantity <= 0:
                    continue
                summary_data.append(
                    {
                        'name':product_name,
                        'total_quantity':total_quantity,
                        'current_stock':product.get('currentStock',0)
                    }
                )
            print(summary_data)
            
            additional_details = {
                "order_count" : order_count,
                "customers_list":customers_list,
                "broken_orders":broken_orders
            }
            return render_template('summary_product.html',data=summary_data, startDate = startDate, endDate = endDate, additional_details = additional_details, user_type = session['role'])
         
        # sort by customer, archived
        else:
            OrderData = MClient['ArchivedInvoices'].find(
                {
                    'deliveryDate':{
                        '$gte':startDate,
                        '$lte':endDate
                    }
                }
            )
            customer_totals = {}
            ProductsData = ProductsDataRaw.find()
                
            # calculating quantities of products and hampers (seperately) for each customer
            broken_orders = []
            for order in OrderData:
                if order['invoiceType'] == 'broken':
                    broken_orders.append(order)
                    continue
                customer_key = str(order['custID']) + order['customer_name']
                tmp_order_total = 0.0
                
                if customer_key not in customer_totals.keys():
                    customer_totals[customer_key] = {
                        'customer_name':order['customer_name'],
                        'customer_address':order['customer_address'],
                        'products_quantity':{},
                        'total_spent':0.0
                    }
                
                for product in order.get('products',[]):
                    product_id = str(product['_id'])
                    product_name = product['product_name']
                    product_key = product_id + '&%$' + product_name
                    
                    quantity = product.get('quantity',0)
                    price_name = product['price_type']
                    price_value = product['price_value']
                    product_discount = product.get('discount',0)
                    tmp_price = price_value * (1 - (product_discount * 0.01))
                    tmp_order_total = tmp_order_total + (quantity * tmp_price)
                    
                    customer_totals[customer_key]['products_quantity'][product_key] = customer_totals[customer_key]['products_quantity'].get(product_key, 0) + quantity
                    
                
                for hamper in order.get('hampers',[]):
                    hamper_id = str(hamper['_id'])
                    hamper_name = hamper['hamper_name']
                    hamper_key = hamper_id + '&%$' + hamper_name

                    quantity = hamper['quantity']
                    price_name = hamper['price_type']
                    price_value = hamper['price_value']
                    hamper_discount = hamper.get('discount',0)
                    tmp_price = price_value * (1 - (hamper_discount * 0.01))
                    tmp_order_total = tmp_order_total + (quantity * tmp_price)
                    
                    customer_totals[customer_key]['products_quantity'][hamper_key] = customer_totals[customer_key]['products_quantity'].get(hamper_key, 0) + quantity
                    
                customer_totals[customer_key]['total_spent'] += tmp_order_total * (1 - (order['orderDiscount'] * 0.01))

            customer_totals = customer_totals.items()
            customer_totals = sorted(customer_totals, key=lambda x:x[1]['total_spent'], reverse=True)
            for customer in customer_totals:
                customer[1]['products_quantity'] = dict(sorted(customer[1]['products_quantity'].items(), key=lambda x:x[1], reverse=True))
            
            return render_template('summary_customer.html',data=customer_totals, startDate = startDate, endDate = endDate, user_type = session['role'], broken_orders = broken_orders)
        
@app.route('/view_broken',methods=["POST"])
@restricted_access(['admin','invoiceAdmin','orderAdmin'])
def view_broken():
    broken_orders = eval(request.form.get('broken_orders'))
    print(broken_orders)
    result = broken_orders
    for order in result:
        if order['invoiceType'] == 'broken':
            order['products'] = order['items']
            order['hampers'] = []
            for item in order['products']:
                item['product_name'] = item['name']
                item['price_type'] = 'custom'
        order['order_total'] = calculate_order_total(order)
    result_sorted = sorted(result, key=lambda x: datetime.strptime(x['deliveryDate'], '%Y-%m-%d'))
    return render_template('view_broken.html',data = result_sorted, user_type = session['role'])

#ENDGROUP: SUMMARY

####################################################################

#GROUP: ADDITIONAL FEATURES
@app.route('/managePayments',methods=['GET'])
@restricted_access(['admin','orderAdmin'])
def manage_payments():
    page = int(request.args.get('page', 1))
    start_index = (page - 1) * 3
    end_index = start_index + 3
    
    orders_collection = MClient['Invoices']
    products_collection = MClient['Products']
    hampers_collection = MClient['Hampers']
    customers_collection = MClient['Customers']
    
    result = []

    for order in orders_collection.find():
        if order['invoiceType'] != 'broken':
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
                'orderDiscount': order.get('orderDiscount', 0.0),
                'paidAmount':order.get('paidAmount',0.0)
            })
        else:
            for product in order['items']:
                product['product_name'] = product['name']
                product['price_name'] = 'custom'
            result.append({
                '_id': order['_id'],
                'customer_name': order['customer_name'],
                'customer_address': order['customer_address'],
                'deliveryDate': order['deliveryDate'],
                'products': order['items'],
                'hampers': [],
                'orderDiscount': order.get('orderDiscount', 0.0),
                'paidAmount':order.get('paidAmount',0.0)
            })

    # calculating order total :/
    for order in result:
        order['order_total'] = calculate_order_total(order)
    result_sorted = sorted(result, key=lambda x: datetime.strptime(x['deliveryDate'], '%Y-%m-%d'))
    
    # for specific date handling
    target_dates = []
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
    
    # pprint.PrettyPrinter(width=50).pprint(filtered_orders)
    print(len(filtered_orders))
    total_pages = math.ceil(len(filtered_orders) / 3.0)
    return render_template('manage_payments.html',data = filtered_orders[start_index:end_index], page=page, user_type = session['role'], total_pages = total_pages, target_dates = target_dates)

@app.route('/managePaymentsEdit/<poID>',methods=['POST'])
@restricted_access(['admin','orderAdmin'])
def edit_payment(poID):
    if request.form.get('access','') == 'get':
        total = request.form.get('final_total')
        paid_amount = request.form.get('paid_amount',0.0)
        data = {
            '_id':poID,
            'total':total,
            'paid_amount':paid_amount
        }
        print(data)
        return render_template('manage_payment_edit.html',data=data,user_type = session['role'])
    else:
        if request.form.get('isFullyPaid'):
            MClient['Invoices'].update_one({'_id':ObjectId(poID)},{
                '$set':{
                    'paidAmount':float(request.form.get('total'))
                }
            })
            return redirect(f'/archive_invoice/{poID}')
        
        paid_amount = request.form.get('paid_amount')
        print(paid_amount, 'paid_amount')
        if not paid_amount:
            return redirect('/managePayments')
        MClient['Invoices'].update_one({'_id':ObjectId(poID)},{
            '$set':{
                'paidAmount':float(paid_amount)
            }
        })
        if request.form.get('isFullyPaid'):
            return redirect(f'/archive_invoice/{poID}')
        else:
            return redirect('/managePayments')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Initialize user data
        users_collection = list(MClient['Users'].find())
        users = {}
        for user in users_collection:
            users[user['username']] = {'password':user['password'], 'role':user['role']}
        print(users)
        
        username = request.form['username']
        password = request.form['password']

        user = next((user for user in users if user.upper() == username.upper() and users[user]['password'] == password), None)

        if user:
            session['username'] = user
            session['role'] = users[user]['role']
            session.permanent = True
            app.permanent_session_lifetime = timedelta(minutes=15)
            if session['role'] in ['invoiceUser','invoiceAdmin']:
                return redirect('/dashboard_invoice')
            elif session['role'] in ['orderAdmin','orderUser']:
                return redirect('/dashboard_order')
            else:
                return redirect('/dashboard')

        flash('Invalid username or password', 'error')
    
    
    message = get_flashed_messages()
    print(type(message))
    if message:
        message = message[-1]
    return render_template('login.html',message = message)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('last_access_time', None)
    print(session)
    return render_template('logout.html')
    
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)