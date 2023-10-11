import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# i am adding notes why is it not working 

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():

    """Show portfolio of stocks"""
    # delete the values from the portfolio
    db.execute("DELETE FROM portfolio")

    # select stocks from transactions
    stocks = db.execute("SELECT DISTINCT stock FROM transactions WHERE user_id IS ?", session["user_id"])

    # find current time
    current_datetime = datetime.datetime.now()

    # Loop this insert values in portfolio database
    for stock in stocks:
        updated_price = lookup(stock['stock'])
        db.execute("INSERT INTO portfolio (stock, live_price, time, date) VALUES (?, ?, ?, ?)",
                    stock['stock'],
                    updated_price['price'],
                    current_datetime.time(),
                    current_datetime.date())

    # select portfolio
    live_portfolio = db.execute("SELECT * FROM transactions JOIN portfolio ON transactions.stock = portfolio.stock WHERE user_ID IS ? AND shares != 0", session['user_id'])

    # create total value dict
    for row in live_portfolio:
        value = row['shares'] * row['live_price']
        db.execute("UPDATE transactions SET live_value = ? WHERE stock = ?", value, row['stock'])

    # reselect portfolio
    live_portfolio = db.execute("SELECT * FROM transactions JOIN portfolio ON transactions.stock = portfolio.stock WHERE user_ID IS ? AND shares != 0", session['user_id'])

    # select cash
    current_cash = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])
    current_cash = current_cash[0]

    # calculate total value
    total_live_value = 0
    for row in live_portfolio:
        total_live_value += row['live_value']

    return render_template("index.html", live_portfolio=live_portfolio, total_live_value=total_live_value, current_cash=current_cash, usd=usd)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # handle post requests
    if request.method == 'POST':

        # make sure symbol is in lookup
        if lookup(request.form.get('symbol')) == None:
            return apology("put the stonk in the thing", 400)

        # check shares are correct
        shares = request.form.get('shares')
        try:
            shares = int(shares)
        except ValueError:
            return apology("not integer", 400)

        if int(request.form.get('shares')) <= 0:
            return apology("0 or smaller", 400)

        # check current stock price
        current_stock_price = float(lookup(request.form.get('symbol'))['price'])

        # select the amount of cash in users
        rows = db.execute('SELECT cash FROM users WHERE id IS ?', session["user_id"])

        if rows == None:
            return apology("got no money m8")
        else:
            user_cash = int(rows[0]['cash'])

        # cost = shares * price
        cost = float(request.form.get('shares')) * current_stock_price

        # compare the shares cost to the users wallet if rejected send apology
        if cost > user_cash:
            return apology("not enough money m8, buy the lidl version", 400)

        # find current time
        current_datetime = datetime.datetime.now()

        # substract stock buy from current cash
        user_cash = user_cash - cost,

        # buy string
        buy = "BUY"

        # store the input into the sql transactions database
        db.execute("INSERT INTO transactions (user_id, stock, price, shares, cost, cash, time, date, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   session["user_id"],
                   request.form.get('symbol').upper(),
                   current_stock_price,
                   request.form.get('shares'),
                   cost,
                   user_cash,
                   current_datetime.time(),
                   current_datetime.date(),
                   buy)

        # update user database
        db.execute("UPDATE users SET cash = ? WHERE id = ?",
                   user_cash,
                   session["user_id"])

        # store the input in history database
        db.execute("INSERT INTO history (user_id, stock, price, shares, value, total_cash, time, date, trans) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   session["user_id"],
                   request.form.get('symbol').upper(),
                   current_stock_price,
                   request.form.get('shares'),
                   cost,
                   user_cash,
                   current_datetime.time(),
                   current_datetime.date(),
                   buy)

        #send info to the buy.html
        return redirect('/')

    else:
        return render_template("buy.html", usd=usd)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    histories = db.execute("SELECT * FROM history WHERE user_id = ?", session['user_id'])

    return render_template("history.html", histories=histories, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html", usd=usd)


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

    # user reached page via POST by submitting form
    if request.method == 'POST':

        # ensure correct usage
        if not request.form.get('symbol'):
            return apology('whoops how did you end up here?')

        # lookup
        quote_dict = lookup(request.form.get('symbol'))

        # reponse if no quote is found
        if quote_dict == None:
            return apology("Lookup could not find your stock", 400)


        return render_template("quoted.html", name=quote_dict['name'], price=quote_dict['price'], symbol=quote_dict['symbol'], usd=usd)

    else:
        return render_template("quote.html", usd=usd)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # user reached page via POST by submitting a form
    if request.method == 'POST':

        #ensure that username is submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        #ensure that password is submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        #ensure that password is submitted
        elif not request.form.get("confirmation"):
            return apology("must provide confirmation", 400)

        #query database for for username
        username = request.form.get('username')
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
        print(len(rows))

        #ensure username doesn't already exist
        if len(rows) > 0:
            return apology('Username is already taken', 400)

        # ensure password is typed correctly both times
        if not request.form.get("password") == request.form.get("confirmation"):
            return apology('Passwords do not match')

        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get('username'), generate_password_hash(request.form.get('password')))

        #redirect to homepage
        return redirect('/')

    else:
        return render_template("register.html", usd=usd)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # select stocks from transactions
    distinct_stocks = db.execute("SELECT DISTINCT stock FROM transactions WHERE user_id IS ?", session["user_id"])

    #handle post requests
    if request.method == 'POST':

        # check shares are correct
        shares = request.form.get('shares')
        try:
            shares = int(shares)
        except ValueError:
            return apology("not integer", 400)

        if int(request.form.get('shares')) <= 0:
            return apology("0 or smaller", 400)


        # check the user has the stock they submitted
        check_stock = db.execute("SELECT * FROM transactions WHERE user_id = ? AND type ='BUY' AND stock = ? AND shares >= ? AND shares != 0",
                                session["user_id"],
                                request.form.get('symbol').upper(),
                                request.form.get('shares'))
        if not check_stock:
            return apology("you do not own this stock or you're trying to buy too much", 400)

        # check current stock price
        current_stock_price = float(lookup(request.form.get('symbol'))['price'])

        # select current cash from user
        user_cash = db.execute('SELECT cash FROM users WHERE id IS ?', session["user_id"])

        # shares * live value
        sell_value = float(current_stock_price) * float(request.form.get('shares'))

        # update user cash
        user_cash = user_cash[0]['cash'] + sell_value

        # find current time
        current_datetime = datetime.datetime.now()

        # send to user database
        sell = 'SELL'

        # update the share value of original transaction from the database
        updated_shares = float(check_stock[0]['shares']) - float(request.form.get('shares'))
        updated_cost = check_stock[0]['cost'] - sell_value


        # UPDATE PORTOFOLIO
        db.execute("UPDATE transactions SET shares = ?, cost = ?, cash = ?, time = ?, date = ? WHERE trans_id = ?",
                   updated_shares,
                   updated_cost,
                   user_cash,
                   current_datetime.time(),
                   current_datetime.date(),
                   check_stock[0]['trans_id'])

        # send to history database
        db.execute("INSERT INTO history (user_id, stock, price, shares, value, total_cash, time, date, trans) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   session['user_id'],
                   request.form.get('symbol').upper(),
                   current_stock_price,
                   request.form.get('shares'),
                   sell_value,
                   user_cash,
                   current_datetime.time(),
                   current_datetime.date(),
                   sell)

        #update user databsae
        db.execute("UPDATE users SET cash = ? WHERE id = ?",
            user_cash,
            session["user_id"])



        return redirect("/")

    else:
        return render_template("sell.html", usd=usd, distinct_stocks=distinct_stocks)

@app.route("/password", methods=["GET", "POST"])
def change_password():
    """Register user"""

    # user reached page via POST by submitting a form
    if request.method == 'POST':

        #ensure that username is submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        #ensure that old password is submitted
        elif not request.form.get("old_password"):
            return apology("must provide password", 400)

        #ensure that new password is submitted
        elif not request.form.get("new_password"):
            return apology("must provide password", 400)

        elif request.form.get("old_password") == request.form.get("new_password"):
            return apology("That's the same as the last password silly", 400)

        #query database for for username
        rows = db.execute("SELECT * FROM users WHERE username IS ?", request.form.get('username'))

        # check if user is in the database
        if not rows[0]['username'] == request.form.get("username"):
            return apology("User does not exist")

        # check if old password works is correct
        if not check_password_hash(rows[0]['hash'], request.form.get("old_password")):
            return apology("Password is incorrect")

        # update user account password
        db.execute("UPDATE users SET hash = ? WHERE username = ?", generate_password_hash(request.form.get("new_password")), request.form.get("username"))

        #redirect to homepage
        return redirect('/login')

    else:
        return render_template("change_password.html", usd=usd)