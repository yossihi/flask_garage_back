# modules imports ---------------------------------------------------------->

import datetime 
import time,os
from functools import wraps
from flask import Flask, current_app, jsonify, request, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.utils import secure_filename
import jwt
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required

# Flas initiation ------------------------------------------------------->

app = Flask(__name__)
app.secret_key = 'secret_secret_key'


# SQLAlchemy configuration --------------------------------------------------------------------->
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///myProject.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'secret_secret_key'
app.config['UPLOAD_FOLDER'] = '/static/images'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)


# Get the directory where app.py is located
app_directory = os.path.dirname(__file__)

# SQLalchemy models ---------------------------------------->

class Books(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String(50))
    Author = db.Column(db.String(50))
    Year_published = db.Column(db.Integer)
    book_Type = db.Column(db.Integer)
    loaned = db.Column(db.Boolean)
    photo = db.Column(db.String(500))
    loans = db.relationship("Loans", backref="book", cascade="all, delete-orphan")


    def __init__(self, Name, Author, Year_published, book_Type, loaned=False, photo="unknown.jpeg"):
        self.Name = Name
        self.Author= Author
        self.Year_published= Year_published
        self.book_Type = book_Type
        self.loaned = loaned
        self.photo = photo

class Customers(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    Name = db.Column(db.String(50))
    City = db.Column(db.String(50))
    Age = db.Column(db.Integer)
    loans = db.relationship("Loans", backref="customer", cascade="all, delete-orphan")

class Loans(db.Model):
    __tablename__ = 'loans'
    id = db.Column(db.Integer, primary_key=True)
    CustID = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    BookID = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    Loandate = db.Column(db.Integer)
    Returndate = db.Column(db.Integer)

    def __init__(self, Book, Customer):
        self.CustID = Customer.id
        self.BookID = Book.id
        self.Loandate = self._get_current_date()
        self.Returndate = self._calculate_return_date(Book.book_Type)

    def _get_current_date(self):
        return datetime.datetime.now().strftime('%m/%d')
    

    def _calculate_return_date(self, book_type):
        loandate = datetime.datetime.now()

        # Define different return date calculations based on book type
        if book_type == 1:
            return (loandate + datetime.timedelta(days=10)).strftime('%m/%d')
        elif book_type == 2:
            return (loandate + datetime.timedelta(days=5)).strftime('%m/%d')
        elif book_type == 3:
            return (loandate + datetime.timedelta(days=2)).strftime('%m/%d')
        elif book_type == -2:
            return (loandate + datetime.timedelta(days=-2)).strftime('%m/%d')

        
    def is_late(self):
        if self.Returndate:
            returndate_datetime = datetime.datetime.strptime(self.Returndate, '%m/%d').replace(year=datetime.datetime.now().year)
            return datetime.datetime.now() > returndate_datetime
        else:
            return False

#---------------------------------------------------------
# create the models and initial admin
with app.app_context():
    db.create_all()
    initial_admin = Customers.query.get(1)
    if not initial_admin:
        new_customer = Customers()
        new_customer.username = "yossi"
        new_customer.password = bcrypt.generate_password_hash("123").decode('utf-8')
        new_customer.is_admin = True
        new_customer.Name = "yossi"
        new_customer.City = "TLV"
        new_customer.Age = 31
        db.session.add(new_customer)
        db.session.commit()

# Generate a JWT
def generate_token(user_id):
    expiration = int(time.time()) + 3600  # Set the expiration time to 1 hour from the current time
    payload = {'user_id': user_id, 'exp': expiration}
    token = jwt.encode(payload, 'secret-secret-key', algorithm='HS256')
    return token

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            current_user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401


        return f(current_user_id, *args, **kwargs)


    return decorated

# opening cors to everyone for tests
CORS(app)

# flask endponts ------------------------------------------------------------------------------------>
@app.route('/is_admin')
@jwt_required()
def admin_check():
    # return a boolen value if the user is admin or not
    checked_cust = Customers.query.filter_by(id=get_jwt_identity()).first()
    return jsonify({"is_admin": checked_cust.is_admin})

@app.route('/login', methods=['POST'])
def login():
    data =request.get_json()
    username = data["username"]
    password = data["password"]
    # Check if the user exists
    user = Customers.query.filter_by(username=username).first()


    if user and bcrypt.check_password_hash(user.password, password):
        # Generate an access token with an expiration time
        expires = datetime.timedelta(hours=1)
        access_token = create_access_token(identity=user.id, expires_delta=expires)
        return jsonify({'access_token': access_token,
                         'message': 'Logged in succefuly',
                           "user_name": user.Name})
    else:
        return jsonify({'message': 'Invalid username or password'})

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    password = data['password']
    Name = data['Name']
    City = data['City']
    Age = data['Age']
    
    # Check if the username is already taken
    existing_user = Customers.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'message': 'Username is already taken'}), 400


    # Hash and salt the password using Bcrypt
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    # Create a new user and add to the database
    new_user = Customers(username=username, password=hashed_password, Name=Name, City=City, Age=Age)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'User created successfully'})

@app.route('/static/images/<filename>', methods=['GET'])
def get_image(filename):
    # return the image file path
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/getBooks")
@jwt_required()
def getBooks():
    if admin_check:
        books = Books.query.all()
        books = [
            {
                "id": book.id,
                "name": book.Name,
                "author": book.Author,
                "year_pub": book.Year_published,
                "book_type": book.book_Type,
                "photo": url_for('get_image', filename=book.photo)
            }for book in books
        ]
        # return list of all the existent books
        return jsonify({"books": books, "message": "books loaded succefuly"})
    else:
        return jsonify({"books": [], "message": "you need an admin privileges"})

@app.route("/add_book", methods=['POST'])
@jwt_required()
def add_book():
    if admin_check():
        # create a new book:
        new_book = Books(Name= request.form['name'],
                        Author= request.form["author"],
                        Year_published= request.form["year"],
                        book_Type= request.form["book_type"])
        # check if the user added a photo
        if 'file' in request.files:
            image = request.files['file']
            if image:
                filename = secure_filename(image.filename)
                image.save(os.path.join(current_app.root_path, 'static/images', filename))
                # add the path of the uploaded photo
                new_book.photo = filename

        db.session.add(new_book)
        db.session.commit()

        return jsonify({"message": "book added succefuly"})
    else:
        return jsonify({"message": "you need an admin privileges"})

@app.route("/edit_book/<int:bookID>", methods=['POST'])
@jwt_required()
def edit_book(bookID):
    if admin_check():
        # search for the book:
        book = Books.query.get_or_404(bookID)
        
        # update the details the user sent
        if "name" in request.form:
            book.Name = request.form["name"]
        if "author" in request.form:
            book.Author = request.form["author"]
        if "year" in request.form:
            book.Year_published = request.form["year"]
        book.book_Type = request.form["book_type"]
        
        if 'file' in request.files:
                image = request.files['file']
                if image:
                    filename = secure_filename(image.filename)
                    image.save(os.path.join(current_app.root_path, 'static/images', filename))
                    book.photo = filename

        db.session.commit()

        return jsonify({"message": "book updated succefuly"})
    else:
        return jsonify({"message": "you need an admin privileges"})

@app.route('/deleteBook/<int:bookID>', methods=['DELETE'])
@jwt_required()
def deleteBook(bookID):
    if admin_check():
        # search a book to delete
        del_book = Books.query.get_or_404(bookID)
        # delete it...
        db.session.delete(del_book)
        db.session.commit()

        return jsonify({"message": "book deleted succefuly"})
    else:
        return jsonify({"message": "you need an admin privileges"})

@app.route("/getCustomers")
@jwt_required()
def getCustomers():
    if admin_check():
        customers = Customers.query.all()
        # the list of all customers
        customers_lst = [
            {
                "id": customer.id,
                "name": customer.Name,
                "city": customer.City,
                "age": customer.Age,
                "is_admin": customer.is_admin
            } for customer in customers
        ]
        # convert it to JSON format
        return jsonify({"customers": customers_lst, "message": "books loaded succefuly"})
    else:
        return jsonify({"message": "you need an admin privileges"})

@app.route('/deleteCust/<int:custID>', methods=['DELETE'])
@jwt_required()
def deleteCust(custID):
    if admin_check():
        # delete customer by id
        del_cust = Customers.query.get(custID)
        
        db.session.delete(del_cust)
        db.session.commit()
        return jsonify({"message": "Customer deleted succefuly"})
    else:
        return jsonify({"message": "you need an admin privileges"})

@app.route("/editCust/<int:custID>", methods=['POST'])
@jwt_required()
def editCust(custID):
    if admin_check():
        # function that change the user authorisation level
        admin_data = request.get_json()
        # convert the json js string to boolean value in python
        py_convers = {"true": True, "false": False}

        changeCust = Customers.query.filter_by(id=custID).first()

        changeCust.is_admin = py_convers[admin_data["is_admin"]]

        db.session.commit()

        return jsonify({"message": "Customer became an Admin"})
    else:
        return jsonify({"message": "you need an admin privileges"})

@app.route("/add_loan", methods=['POST'])
@jwt_required()
def add_loan():
    loan_data = request.get_json()
    # get the correct Book and Customer
    Book = Books.query.filter_by(Name=loan_data["book"]).first()
    Book.loaned = True
    customer = Customers.query.filter_by(id=get_jwt_identity()).first()
    if Book and customer:

        new_loan = Loans(Book=Book, Customer=customer)
    
        db.session.add(new_loan)
        db.session.commit()
        
        return jsonify({"message": 'loan added successfully'})
    else:
        return jsonify({"message": "Invalid book or customer"}) 

@app.route("/get_loans")
@jwt_required()
def get_loans():
    if admin_check():
        # function that get all the active loans of all customers 
        loans = Loans.query.all()
        loans_data = []
        for loan in loans:
            book_loan = Books.query.filter_by(id=loan.BookID).first()
            cust_loan = Customers.query.filter_by(id=loan.CustID).first()
            loans_data.append({
                "id": loan.id,
                "book_name": book_loan.Name,
                "cust_name": cust_loan.Name,
                "loan_date": loan.Loandate,
                "Returndate": loan.Returndate,
                "is_late": loan.is_late()
            })
        return jsonify({"loans": loans_data, "message": "loan's loaded succefuly"})
    else:
        return jsonify({"message": "you need an admin privileges"})

@app.route("/unloan_books")
@jwt_required()
def unloan_books():
    # return list of unloan books to be display the user to loan
    unloans = Books.query.filter_by(loaned= False)
    book_types = {"1": "10 days", "2": "5 days", "3": "2 days", "-2": "in late"}
    unloans = [
        {
            "id": book.id,
            "name": book.Name,
            "author": book.Author,
            "year_pub": book.Year_published,
            "photo": url_for('get_image', filename=book.photo),
            "return_day": book_types[str(book.book_Type)]
        }for book in unloans
    ]
    return jsonify({"books": unloans, "message": "unloaned books loaded succefuly"})

@app.route('/return_loan/<int:loanID>', methods=['DELETE'])
@jwt_required()
def return_loan(loanID):
    # delete the loan and change the 'loaned' of the book to false
    del_loan = Loans.query.get(loanID)
    returnd_book =  Books.query.filter_by(id=del_loan.BookID).first()
    returnd_book.loaned = False
    db.session.delete(del_loan)
    db.session.commit()

    return jsonify({"message": "loan returned succefuly"})

@app.route('/user_loans')
@jwt_required()
def user_loans():
    # return list of active loans of the user
    loans_lst = Loans.query.filter_by(CustID=get_jwt_identity()).all()
    loans_data = []
    for loan in loans_lst:
        loan_book = Books.query.filter_by(id=loan.BookID).first()
        book_name = loan_book.Name
        loans_data.append({"id":loan.id, "name": book_name, "loandate": loan.Loandate, "Returndate": loan.Returndate, "is_late": loan.is_late()})
    return jsonify({"loans": loans_data, "message": "active loans load succefuly"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)