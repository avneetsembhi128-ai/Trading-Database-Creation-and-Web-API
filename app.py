from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import text
import time, datetime

app = Flask(__name__)

psql_user = 'postgres'
psql_password = ''
db_name = 'pits'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://{}:{}@localhost/{}'.format(psql_user, psql_password, db_name)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

@app.route('/')
def index():
    # Execute a raw SQL query directly
    connection = db.engine.raw_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM Stock WHERE sym = 'AAPL';")
    query_result = cursor.fetchall()
    if len(query_result) > 0:
        res = query_result[0]
    else:
        res = []
    return jsonify(res)

@app.route('/getOwner')
def getOwner():
    """
        This HTTP method takes aid as input, and returns all owner's pid in a list
        If the account does not exist, return [{'pid': -1}]
    """
    aid = int(request.args.get('aid', -1))
    res = []
    with db.engine.begin() as conn:
        account_check = conn.execute(text("SELECT 1 FROM Account WHERE aid = :aid ;"),
                                     {'aid': aid}).fetchone()
        if not account_check:
            res = [{'pid': -1}]
        else:
            query_result = conn.execute(text("SELECT pid FROM Owns WHERE aid = :aid"),
                                        {'aid': aid}).fetchall()
            for row in query_result:
                res.append({'pid': int(row[0])})
    return jsonify(res)

@app.route('/getHoldings')
def getHoldings():
    """
        This HTTP method takes aid and sym as input, 
        and returns the total share of holdings for a stock sym of an account
        If the stock does not exist or the account does not exist, return {'shares': -1};
        If the account does not hold any share of the stock, return {'shares': 0}
    """
    aid = int(request.args.get('aid', -1))
    sym = request.args.get('sym', '')
    res = []
    with db.engine.begin() as conn:
        account_check = conn.execute(text("SELECT 1 FROM Account WHERE aid = :aid ;"),
                                     {'aid': aid}).fetchone()
        share_check = conn.execute(text("SELECT 1 FROM Stock WHERE sym = :sym ;"),
                                     {'sym': sym}).fetchone()
        if not account_check or not share_check:
            shares = -1
        else:
            query_result = conn.execute(text("""SELECT SUM (CASE
                    WHEN type = 'buy' THEN shares WHEN type = 'sell' THEN -shares ELSE 0 END) AS total_shares
                    FROM Trade WHERE aid = :aid AND sym = :sym"""),
                                        {'aid': aid, 'sym': sym}).fetchone()
            if query_result[0] is not None:
                shares = float(query_result[0])
            else:
                shares = 0
    return jsonify({'shares': shares})

def currentTime():
    ts = time.time()
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    
@app.route('/trade')
def trade():
    """
        This HTTP method takes the information of a trade as input: aid, sym, type, shares, price 
        It returns {'res' : 'fail'} if there is an oversell or other errors like aid/sym/type does not exist;
        Otherwise, it returns {'res': the current seq} and also updates the database accordingly.
        
    """
    aid = int(request.args.get('aid', -1))
    sym = request.args.get('sym', '')
    type = request.args.get('type', '')
    shares = float(request.args.get('shares', -1))
    price = float(request.args.get('price', -1))

    with db.engine.begin() as conn:
        if type not in ['buy', 'sell']:
            response = "fail"

        acc = conn.execute(text("SELECT 1 FROM Account WHERE aid = :aid"), {'aid': aid}).fetchone()
        stock = conn.execute(text("SELECT 1 FROM Stock WHERE sym = :sym"), {'sym': sym}).fetchone()
        if not acc or not stock:
            response = "fail"

        query_result = conn.execute(text("""SELECT SUM (CASE
                    WHEN type = 'buy' THEN shares WHEN type = 'sell' THEN -shares ELSE 0 END) AS total_shares
                    FROM Trade WHERE aid = :aid AND sym = :sym"""),
                                        {'aid': aid, 'sym': sym}).fetchone()
        total_shares = query_result[0]
        if type == 'sell' and shares > total_shares:
            response = "fail"
        else:
            max_seq = conn.execute(text("SELECT MAX(seq) FROM Trade WHERE aid = :aid"), {'aid': aid}).fetchone()
            conn.execute(text("""
                INSERT INTO Trade (aid, seq, type, timestamp, sym, shares, price)
                VALUES (:aid, :seq, :type, :timestamp, :sym, :shares, :price)
            """), {
                'aid': aid,
                'seq': (max_seq[0] + 1),
                'type': type,
                'timestamp': currentTime(),
                'sym': sym,
                'shares': shares,
                'price': price
            })
            response = max_seq[0] + 1
    response = {"res": response}
    return jsonify(response)

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, port=5000)