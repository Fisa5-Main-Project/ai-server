-- Local fixture; never run this file against a production database.
SET NAMES utf8mb4;
CREATE USER 'debezium'@'%' IDENTIFIED BY 'cdc_demo';
GRANT SELECT, RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT, LOCK TABLES ON *.* TO 'debezium'@'%';

USE knowhow;
CREATE TABLE users (
  user_id BIGINT PRIMARY KEY,
  birth DATE NOT NULL, gender VARCHAR(10) NOT NULL,
  asset_total BIGINT, investment_tendancy VARCHAR(50), user_mydata_registration BOOLEAN
);
CREATE TABLE user_info (
  user_info_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL UNIQUE,
  goal_amount BIGINT, goal_target_date DATE, expectation_monthly_cost BIGINT,
  fixed_monthly_cost BIGINT, retirement_status BOOLEAN, annual_income BIGINT,
  target_retired_age INT, num_dependents INT, mydata_status VARCHAR(30),
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE assets (
  asset_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, type VARCHAR(30) NOT NULL,
  balance DECIMAL(18,2) NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE keyword (keyword_id BIGINT PRIMARY KEY, name VARCHAR(100) NOT NULL);
CREATE TABLE user_keyword (
  user_id BIGINT NOT NULL, keyword_id BIGINT NOT NULL, PRIMARY KEY (user_id, keyword_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (keyword_id) REFERENCES keyword(keyword_id) ON DELETE CASCADE
);
INSERT INTO users VALUES (1, '1990-01-01', 'M', 100000000, '안정추구형', TRUE);
INSERT INTO user_info VALUES (1, 1, 500000000, '2050-01-01', 2000000, 1000000, FALSE, 50000000, 60, 0, 'CONNECTED');
INSERT INTO assets VALUES (1, 1, 'CURRENT', 100000000.00);
INSERT INTO keyword VALUES (1, '안정적 생활비');
INSERT INTO user_keyword VALUES (1, 1);
