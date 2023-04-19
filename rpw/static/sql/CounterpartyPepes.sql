# noinspection SqlNoDataSourceInspectionForFile

DROP DATABASE IF EXISTS CounterpartyPepes;
CREATE DATABASE CounterpartyPepes;
GRANT ALL PRIVILEGES ON CounterpartyPepes.* TO 'cp'@'localhost';
USE CounterpartyPepes;

-- dispensers
DROP TABLE IF EXISTS dispensers;
CREATE TABLE dispensers
(
    id              INTEGER UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    asset           VARCHAR(40)      NOT NULL, -- asset name
    block_index     INTEGER UNSIGNED,
    escrow_quantity BIGINT,                    -- Tokens to escrow in dispenser
    give_quantity   BIGINT,                    -- Tokens to vend per dispense
    give_remaining  BIGINT,
    satoshirate     BIGINT,                    -- Bitcoin satoshis required per dispense
    source          VARCHAR(130)     NOT NULL, -- address of source
    status          TEXT,
    tx_index        INTEGER UNSIGNED,
    tx_hash         VARCHAR(64),                -- id of record in index_transactions
    satoshi_price   INTEGER UNSIGNED
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

CREATE UNIQUE INDEX tx_hash ON dispensers (tx_hash);
CREATE INDEX source ON dispensers (source);
CREATE INDEX asset ON dispensers (asset);

-- assets
DROP TABLE IF EXISTS assets;
CREATE TABLE assets
(
    id                    INTEGER UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    asset                 VARCHAR(40)      NOT NULL, -- asset name
    asset_longname        VARCHAR(255),              -- subasset name
    description           VARCHAR(500),
    divisible             TINYINT(1),
    issuer                VARCHAR(130)     NOT NULL, -- issuer address
    owner                 VARCHAR(130)     NOT NULL, -- owner address
    source                VARCHAR(130)     NOT NULL, -- original issuer address
    locked                TINYINT(1),
    supply                BIGINT UNSIGNED,
    series                TINYINT(6),
    rarepepedirectory_url VARCHAR(125),
    image_file_name       VARCHAR(43)      NOT NULL,
    real_supply           BIGINT UNSIGNED
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

CREATE UNIQUE INDEX asset ON assets (asset);
CREATE INDEX issuer ON assets (issuer);
CREATE INDEX owner ON assets (owner);

-- non pepe asset
INSERT INTO assets (asset, description, divisible, locked, supply, issuer, owner, source, series, image_file_name)
VALUES ('XCP', '', 1, 0, 2613555.59157850, '', '', '', 0, 'XCP.png');

-- holdings
DROP TABLE IF EXISTS holdings;
CREATE TABLE holdings
(
    id               INTEGER UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    address          VARCHAR(130)     NOT NULL, -- address of holder
    asset            VARCHAR(40)      NOT NULL, -- asset name
    address_quantity BIGINT UNSIGNED,           -- amount owned
    escrow           VARCHAR(150)
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

CREATE INDEX address ON holdings (address);
CREATE INDEX asset ON holdings (asset);

-- orders
DROP TABLE IF EXISTS orders;
CREATE TABLE orders
(
    tx_index               INTEGER UNSIGNED,
    tx_hash                TEXT,
    block_index            INTEGER UNSIGNED,
    source                 VARCHAR(130),
    give_asset             TEXT,
    give_quantity          BIGINT,
    give_remaining         BIGINT,
    get_asset              TEXT,
    get_quantity           BIGINT,
    get_remaining          BIGINT, -- handles negative integers
    expiration             INTEGER UNSIGNED,
    expire_index           INTEGER UNSIGNED,
    fee_required           BIGINT,
    fee_required_remaining BIGINT,
    fee_provided           BIGINT,
    fee_provided_remaining BIGINT,
    status                 VARCHAR(100)
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

CREATE UNIQUE INDEX tx_index ON orders (tx_index);
CREATE INDEX block_index ON orders (block_index);

-- addresses
DROP TABLE IF EXISTS addresses;
CREATE TABLE addresses
(
    id      INTEGER UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    address VARCHAR(120)     NOT NULL, -- address string
    is_burn TINYINT(1)
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

CREATE UNIQUE INDEX address ON addresses (address);

-- currency prices
DROP TABLE IF EXISTS prices;
CREATE TABLE prices
(
    currency    CHAR(8),
    description VARCHAR(50),
    usd_rate    FLOAT(13, 8)
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

-- initial prices data
INSERT INTO prices (currency, description, usd_rate)
VALUES ('BTC', 'Bitcoin', 0);
INSERT INTO prices (currency, description, usd_rate)
VALUES ('XCP', 'Counterparty', 0);
INSERT INTO prices (currency, description, usd_rate)
VALUES ('PEPECASH', 'Pepecash', 0);

-- ad slots
DROP TABLE IF EXISTS ad_slots;
CREATE TABLE ad_slots
(
    slot_number  TINYINT,
    asset        VARCHAR(40) NOT NULL, -- asset name
    block_remain INTEGER UNSIGNED,
    paid_invoice VARCHAR(30)
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

-- default starting values
INSERT INTO ad_slots (asset, slot_number, block_remain, paid_invoice)
VALUES ('_RANDOM_', 1, 0, '__default__');
INSERT INTO ad_slots (asset, slot_number, block_remain, paid_invoice)
VALUES ('PUMPURPEPE', 2, 0, '__default__');
INSERT INTO ad_slots (asset, slot_number, block_remain, paid_invoice)
VALUES ('PEPETRADERS', 3, 0, '__default__');

-- ad queue
DROP TABLE IF EXISTS ad_queue;
CREATE TABLE ad_queue
(
    id           INTEGER UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    asset        VARCHAR(40)      NOT NULL,
    block_amount INTEGER UNSIGNED,
    paid_invoice VARCHAR(30)
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

-- ad history
DROP TABLE IF EXISTS ad_history;
CREATE TABLE ad_history
(
    id           INTEGER UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    asset        VARCHAR(40)      NOT NULL,
    block_amount INTEGER UNSIGNED,
    paid_invoice VARCHAR(30)
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;

-- ad slot history
DROP TABLE IF EXISTS ad_slot_history;
CREATE TABLE ad_slot_history
(
    block_level INTEGER UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    slot1       VARCHAR(40)      NOT NULL,
    slot2       VARCHAR(40)      NOT NULL,
    slot3       VARCHAR(40)      NOT NULL
) ENGINE = MyISAM
  DEFAULT CHARSET = utf8
  COLLATE = utf8_unicode_ci;