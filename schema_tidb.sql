-- EnergyPro - same tables as schema.sql, for the TiDB Cloud SQL Editor.
-- Every table name includes the database, so no USE statement is needed.
-- Safe to run more than once.

CREATE DATABASE IF NOT EXISTS smart_hostel_v2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_hostel_v2.users (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(80)  NOT NULL,
  roll_no     VARCHAR(20)  NULL,
  room        VARCHAR(20)  NULL,
  rfid_uid    VARCHAR(32)  NOT NULL UNIQUE,
  balance     DECIMAL(14,6) NOT NULL DEFAULT 0,
  active      TINYINT(1)   NOT NULL DEFAULT 1,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS smart_hostel_v2.device_state (
  id               INT PRIMARY KEY,
  name             VARCHAR(40)  NOT NULL DEFAULT 'Room Node',
  relay_on         TINYINT(1)   NOT NULL DEFAULT 0,
  active_user_id   INT          NULL,
  last_energy_wh   DOUBLE       NULL,
  total_energy_wh  DOUBLE       NOT NULL DEFAULT 0,
  total_spent      DECIMAL(14,6) NOT NULL DEFAULT 0,
  fault            TINYINT(1)   NOT NULL DEFAULT 0,
  theft            TINYINT(1)   NOT NULL DEFAULT 0,
  last_seen        DATETIME     NULL,
  ip               VARCHAR(45)  NULL,
  rssi             INT          NULL,
  CONSTRAINT fk_device_user FOREIGN KEY (active_user_id) REFERENCES smart_hostel_v2.users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS smart_hostel_v2.readings (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  device_id   INT          NOT NULL,
  created_at  DATETIME     NOT NULL,
  voltage     FLOAT        NULL,
  current     FLOAT        NULL,
  power       FLOAT        NULL,
  energy_wh   DOUBLE       NULL,
  frequency   FLOAT        NULL,
  pf          FLOAT        NULL,
  relay_on    TINYINT(1)   NOT NULL DEFAULT 0,
  user_id     INT          NULL,
  balance     DECIMAL(14,6) NULL,
  cost        DECIMAL(14,6) NOT NULL DEFAULT 0,
  fault       TINYINT(1)   NOT NULL DEFAULT 0,
  theft       TINYINT(1)   NOT NULL DEFAULT 0,
  INDEX idx_device_id (device_id, id),
  INDEX idx_created (created_at)
);

CREATE TABLE IF NOT EXISTS smart_hostel_v2.transactions (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  user_id        INT          NOT NULL,
  type           VARCHAR(20)  NOT NULL,
  amount         DECIMAL(14,6) NOT NULL,
  balance_after  DECIMAL(14,6) NOT NULL,
  created_at     DATETIME     NOT NULL,
  CONSTRAINT fk_tx_user FOREIGN KEY (user_id) REFERENCES smart_hostel_v2.users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS smart_hostel_v2.events (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  device_id   INT          NOT NULL,
  type        VARCHAR(30)  NOT NULL,
  message     VARCHAR(255) NOT NULL,
  rfid_uid    VARCHAR(32)  NULL,
  user_id     INT          NULL,
  created_at  DATETIME     NOT NULL,
  INDEX idx_events_device (device_id, id)
);

CREATE TABLE IF NOT EXISTS smart_hostel_v2.settings (
  k  VARCHAR(40)  PRIMARY KEY,
  v  VARCHAR(255) NOT NULL
);

INSERT IGNORE INTO smart_hostel_v2.settings (k, v) VALUES
  ('tariff_per_kwh', '8'),
  ('auto_cutoff',    '1'),
  ('low_balance',    '20'),
  ('volt_min',       '180'),
  ('volt_max',       '260'),
  ('theft_current',  '0.010'),
  ('poll_ms',        '2000');

INSERT IGNORE INTO smart_hostel_v2.device_state (id, name) VALUES (1, 'Room A-101');

INSERT IGNORE INTO smart_hostel_v2.users (name, roll_no, room, rfid_uid, balance) VALUES
  ('Demo Student', '000000000', 'A-101', 'DEADBEEF', 100);

SHOW TABLES FROM smart_hostel_v2;
