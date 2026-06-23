
CREATE TABLE Person
(pid DECIMAL(10,0) NOT NULL PRIMARY KEY,
 name VARCHAR(256) NOT NULL,
 address VARCHAR(256) NOT NULL);

CREATE TABLE Broker
(pid DECIMAL(10,0) NOT NULL PRIMARY KEY REFERENCES Person(pid),
 license VARCHAR(20) NOT NULL UNIQUE,
 phone DECIMAL(10,0) NOT NULL,
 manager DECIMAL(10,0) REFERENCES Broker(pid));

CREATE TABLE Account
(aid INTEGER NOT NULL PRIMARY KEY,
 brokerpid DECIMAL(10,0) NOT NULL REFERENCES Broker(pid));

CREATE TABLE Owns
(pid DECIMAL(10,0) NOT NULL REFERENCES Person(pid),
 aid INTEGER NOT NULL REFERENCES Account(aid),
 PRIMARY KEY (pid, aid));

CREATE TABLE Stock
(sym CHAR(5) NOT NULL PRIMARY KEY,
 price DECIMAL(10,2) NOT NULL);

CREATE TABLE Trade
(aid INTEGER NOT NULL REFERENCES Account(aid),
 seq INTEGER NOT NULL,
 type CHAR(4) NOT NULL CHECK(type = 'buy' OR type = 'sell'),
 timestamp TIMESTAMP NOT NULL,
 sym CHAR(5) NOT NULL REFERENCES Stock(sym),
 shares DECIMAL(10,2) NOT NULL,
 price DECIMAL(10,2) NOT NULL,
 PRIMARY KEY (aid, seq));

----------------------------------------------------------------------
-- Since PITS records only completed trades, enforce that the Trade 
-- table is append-only using a trigger. Trades must be recorded 
-- sequentially over time.

CREATE FUNCTION TF_TradeSeqAppendOnly() RETURNS TRIGGER AS $$
BEGIN
 
  IF TG_OP IN ('DELETE', 'UPDATE') THEN
    RAISE EXCEPTION 'trade table is append-only';
  END IF;

  IF NEW.timestamp < (
    SELECT COALESCE(MAX(timestamp), TIMESTAMP 'epoch')
    FROM Trade
    WHERE aid = NEW.aid
  ) THEN
      RAISE EXCEPTION 'timestamp must be no less than previous trades for account';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER TG_TradeSeqAppendOnly
  BEFORE INSERT OR UPDATE OR DELETE ON Trade
  FOR EACH ROW
  EXECUTE PROCEDURE TF_TradeSeqAppendOnly();

----------------------------------------------------------------------
-- Brokers cannot own accounts

CREATE FUNCTION TF_BrokerNotAccountOwner() RETURNS TRIGGER AS $$
BEGIN
  
   IF TG_TABLE_NAME = 'owns' THEN
    IF EXISTS (
      SELECT 1 FROM Broker WHERE pid = NEW.pid
    ) THEN
      RAISE EXCEPTION 'brokers can not own accounts';
    END IF;

  ELSIF TG_TABLE_NAME = 'broker' THEN
    IF EXISTS (
      SELECT 1 FROM Owns WHERE pid = NEW.pid
    ) THEN
      RAISE EXCEPTION 'a new broker can not own an account';
    END IF;
  END IF;
  RETURN NEW;
 
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER TG_BrokerNotAccountOwner_Broker
  BEFORE INSERT OR UPDATE OF pid ON Broker
  -- note that DELETE won't cause a violation
  FOR EACH ROW
  EXECUTE PROCEDURE TF_BrokerNotAccountOwner();

CREATE TRIGGER TG_BrokerNotAccountOwner_Owns
  BEFORE INSERT OR UPDATE OF pid ON Owns
  -- note that DELETE won't cause a violation
  FOR EACH ROW
  EXECUTE PROCEDURE TF_BrokerNotAccountOwner();

----------------------------------------------------------------------
-- Returns the current account holdings from the Trade table.

CREATE VIEW Holds(aid, sym, shares) AS
  
  SELECT aid, sym, SUM(
    CASE
      WHEN type = 'buy' THEN shares
      WHEN type = 'sell' THEN -shares
      ELSE 0
    END
  ) AS shares
  FROM Trade
  GROUP BY aid, sym;

CREATE FUNCTION TF_NoOverSell() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.type = 'sell' AND
     NEW.shares > COALESCE((SELECT shares FROM Holds WHERE aid = NEW.aid AND sym = NEW.sym), 0) THEN
    RAISE EXCEPTION 'cannot sell more than the number of % shares currently held',
                    NEW.sym;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER TG_NoOverSell
  BEFORE INSERT ON Trade
  FOR EACH ROW
  EXECUTE PROCEDURE TF_NoOverSell();
