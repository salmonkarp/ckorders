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

# object creation
app = Flask(__name__)
MClient = pymongo.MongoClient("mongodb+srv://salmonkarp:ESkMTNgD4383kC9@cookieskingdomdb.gq6eh6v.mongodb.net/")['CK']
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
                'price': float(request.form.get('price')),
                'retail_price': float(request.form.get('retail_price'))
            }
            ckProducts.insert_one(new_product)
            return redirect('/')
        
        
        elif product_type == 'hampers':
            hamper_name = request.form.get('hname')
            selected_products = request.form.getlist('products[]')
            ckHampers = MClient['Hampers']
            hamper = {
                'name': hamper_name,
                'price': float(request.form.get('hprice')),
                'retail_price': float(request.form.get('hretail_price')),
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
    ckConn = MClient['Products']
    ckProducts = list(MClient['Products'].find())
    ckHampers = list(MClient['Hampers'].find())
    
    # modifying ckHampers to include product name
    for hamper in ckHampers:
        for item in hamper['items']:
            itemID = item['product_id']
            itemName = list(ckConn.find({
                '_id':ObjectId(itemID)
            },))[0]['name']
            item['name'] = (itemName)
    return render_template("edit_view.html",productsList = ckProducts, hampersList = ckHampers)

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
    ckConn.update_many({
        '_id':ObjectId(productID)
    },{
        '$set':{
            'name':request.form.get('name'),
            'price': float(request.form.get('price')),
            'retail_price': float(request.form.get('retail_price'))
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
        'retail_price': float(request.form.get('hretail_price')),
        'items': []
    }

    for product in all_products:
        product_id = str(product['_id'])
        quantity_key = 'quantity_' + product_id
        new_quantity = int(request.form.get(quantity_key, 0))
        if new_quantity != 0:
            hamper['items'].append({
                'product_id': product_id,
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

    deliveryDate = request.form.get('delivery_date')
    selected_products = request.form.getlist('products[]')
    selected_hampers = request.form.getlist('hampers[]')
    
    OrderObject = {
        'custID':custID,
        'deliveryDate':deliveryDate,
        'products': [],
        'hampers':[]
    }

    for product_id in selected_products:
        quantity_key = 'p_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        
        if quantity > 0:
            OrderObject['products'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity
            })

    for product_id in selected_hampers:
        quantity_key = 'h_quantities_' + product_id
        quantity = int(request.form.get(quantity_key, 0))
        
        if quantity > 0:
            OrderObject['hampers'].append({
                'product_id': ObjectId(product_id),
                'quantity': quantity
            })

    ckPOs = MClient['POs']
    ckPOs.insert_one(OrderObject)

    print(OrderObject)
    return redirect('/')

@app.route("/viewPOs",methods=["GET"])
def viewPOs():
    POData = MClient['POs']
    HampersData = list(MClient['Hampers'].find())
    ProductsData = list(MClient['Products'].find())
    CustomersData = list(MClient['Customers'].find())

    FinalData = {}
    pipeline = [
        {
            '$unwind': '$products'
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
            '$unwind': '$product_details'
        },
        {
            '$group': {
                '_id': '$_id',
                'order_id': {'$first': '$_id'},
                'custID': {'$first': '$custID'},
                'deliveryDate': {'$first': '$deliveryDate'},
                'products': {'$push': {
                    'product_id': '$products.product_id',
                    'quantity': '$products.quantity',
                    'name': '$product_details.name',  # Assuming 'name' is a field in the 'items' collection
                }}
            }
        },
        {
            '$unwind': '$hampers'
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
            '$unwind': '$hamper_details'
        },
        {
            '$group': {
                '_id': '$_id',
                'order_id': {'$first': '$_id'},
                'custID': {'$first': '$custID'},
                'deliveryDate': {'$first': '$deliveryDate'},
                'products': {'$first': '$products'},
                'hampers': {'$push': {
                    'product_id': '$hampers.product_id',
                    'quantity': '$hampers.quantity',
                    'name': '$hamper_details.name',  # Assuming 'name' is a field in the 'items' collection
                }}
            }
        }
    ]
    FinalData = list(POData.aggregate(pipeline))
    pprint.PrettyPrinter(width=50).pprint(FinalData)
    return render_template('view_po.html',data = FinalData)

if __name__ == '__main__':
    app.run()