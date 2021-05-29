import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    userid = session["user_id"]
    stocks = db.execute("SELECT symbol FROM purchase WHERE userid = :userid GROUP BY symbol",
                        userid=userid)
    cash = db.execute("SELECT cash FROM users WHERE id = :userid", userid=userid)
    grand_total = cash[0]["cash"]
    if stocks != []:
        storages = list()
        for symbol in stocks:
            stock_data = lookup(symbol["symbol"])
            current_price = stock_data["price"]
            stock_info = dict()
            shares_info = db.execute("SELECT SUM(shares) AS shares_sum FROM purchase WHERE userid = :userid\
                                      GROUP BY symbol HAVING symbol = :symbol", userid=userid, symbol=symbol["symbol"])
            current_shares = shares_info[0]["shares_sum"]
            if current_shares > 0:
                stock_info["symbol"] = symbol["symbol"]
                stock_info["name"] = stock_data["name"]
                stock_info["price"] = usd(current_price)
                stock_info["shares"] = current_shares
                total = current_price * current_shares
                grand_total += total
                stock_info["total"] = usd(total)
                storages.append(stock_info)
        return render_template("index.html", storages=storages, cash=usd(cash[0]["cash"]), grand_total=usd(grand_total))
    else:
        return render_template("index.html", cash=usd(cash[0]["cash"]), grand_total=usd(grand_total))
    return render_template("index.html")


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    """change user password"""
    userid = session['user_id']
    hashed = db.execute("SELECT hash FROM users WHERE id = :userid", userid=userid)
    new = request.form.get("new")
    confirm = request.form.get("confirm")

    if request.method == "POST":
        if not check_password_hash(hashed[0]['hash'], request.form.get("old")):
            return apology("You inputted the wrong current password",400)
        else:
            success = False
            if new != confirm:
                return apology("Passwords from new and confirm field don't match", 400)
            else:
                updatehash = generate_password_hash(new)
                db.execute("UPDATE users SET hash = :hashed WHERE id = :userid", hashed= updatehash, userid=userid)
                success = True
            if success is True:
                flash("Account password updated!")
                return redirect("/")
            else:
                flash("Password update failure")
                return redirect("/")
    else:
        return render_template("account.html")



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        symbol = request.form.get('symbol')
        shares = int(request.form.get("shares"))
        quote = lookup(symbol)
        userid = session["user_id"]

        if quote is None:
            return apology("Incorrect symbol, try again", 400)
        else:
            rows = db.execute("SELECT cash FROM users WHERE id = :userid",
            userid=userid)
            cash = rows[0]["cash"]
            price = quote["price"]
            tot = price * shares

            if cash < tot:
                return apology("you can't afford this stock")
            else:
                db.execute("UPDATE users SET cash = cash - :tot WHERE id = :userid", tot=tot, userid=userid)
                db.execute("""INSERT INTO purchase (userid, symbol, shares, tot)
                            VALUES (:userid, :symbol, :shares, :tot)""", userid=userid,
                            symbol=symbol, shares=shares, tot=tot)
                flash("Bought!")
                return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    userid = session["user_id"]
    transactions = db.execute("SELECT * FROM purchase WHERE userid = :userid", userid = userid)
    for transaction in transactions:
        transaction["price"] = usd(transaction["tot"]/transaction["shares"])
        transaction["name"] = lookup(transaction["symbol"])['name']
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid stock symbol")
        else:
            return render_template("quoted.html", stock=stock)
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    session.clear()

    # POST register
    if request.method == "POST":

        # function to check if username already exists in database
        def usernameexists():
            users = db.execute("SELECT username FROM users WHERE username = :username",
                                username=request.form.get("username"))
            # checks if username exists already
            if len(users) == 1:
                return True

        # Ensure unique username was submitted
        if usernameexists():
            return apology("Provide a username that hasn't been taken", 403)

        # Ensure password was submitted
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Check passwords and confirmation boxes again, they must match", 403)

        # Query database for username
        else:
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                          username=request.form.get("username"), password=generate_password_hash(request.form.get("password")))
             # Query database for username
            rows = db.execute("SELECT id FROM users WHERE username = :username",
                          username=request.form.get("username"))
            session["user_id"] = rows[0]
            flash("Registered!!")
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    userid = session["user_id"]
    stocks = db.execute("SELECT symbol FROM purchase WHERE userid = :userid GROUP BY symbol",userid=userid)

    if request.method == "POST":
        symbol_sell = request.form.get("symbol")
        shares_sell = float(request.form.get("shares"))
        shares_info = db.execute("SELECT SUM(shares) AS shares_sum FROM purchase\
                                WHERE userid = :userid GROUP BY symbol HAVING symbol = :symbol", userid=userid, symbol=symbol_sell)
        if shares_info[0]["shares_sum"] < shares_sell:
            return apology("You don't have that many shares", 400)
        else:
            current = lookup(symbol_sell)
            price = current["price"]
            amount = -shares_sell * price
            cash = db.execute("SELECT cash FROM users WHERE id =:userid", userid=userid)
            balance = cash[0]["cash"] - amount
            db.execute("INSERT INTO purchase (userid, symbol, shares, tot) VALUES(:userid, :symbol, :shares, :tot)",
                        userid=userid, symbol=symbol_sell, shares=-shares_sell, tot=amount)
            db.execute("UPDATE users SET cash = :balance WHERE id = :userid", balance=balance, userid=userid)
            flash("SOLD!!")
            return redirect("/")
    else:
        list_symbol = list()
        for symbol in stocks:
            shares_info = db.execute("SELECT SUM(shares) AS shares_sum FROM purchase\
                                        WHERE userid = :userid GROUP BY symbol HAVING symbol = :symbol", userid = userid, symbol=symbol["symbol"])
            current_shares = shares_info[0]
            if shares_info[0]["shares_sum"]:
                list_symbol.append(symbol["symbol"])
        return render_template("sell.html", list_symbol=list_symbol)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

