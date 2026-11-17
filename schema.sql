-- EnergyPro - Smart Hostel Electricity Control System
-- MySQL / MariaDB schema. Import with phpMyAdmin (Import tab) or:
--   mysql -u root < schema.sql

CREATE DATABASE IF NOT EXISTS smart_hostel_v2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE smart_hostel_v2;

-- Registered students (one RFID card each) and their prepaid balance.
-- Balances use 6 decimal places because one 2-second reading of a 7 W bulb
-- costs only a few thousandths of a paisa.
CREATE TABLE IF NOT EXISTS users (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(80)  NOT NULL,
  roll_no     VARCHAR(20)  NULL,
  room        VARCHAR(20)  NULL,
  rfid_uid    VARCHAR(32)  NOT NULL UNIQUE,
  balance     DECIMAL(14,6) NOT NULL DEFAULT 0,
  active      TINYINT(1)   NOT NULL DEFAULT 1,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Live state of each room node (the prototype has one node, id = 1).
-- The server is the source of truth for relay_on; the ESP32 applies it on every sync.
CREATE TABLE IF NOT EXISTS device_state (
  id               INT PRIMARY KEY,
  name             VARCHAR(40)  NOT NULL DEFAULT 'Room Node',
  relay_on         TINYINT(1)   NOT NULL DEFAULT 0,
  active_user_id   INT          NULL,
  last_energy_wh   DOUBLE       NULL,     -- PZEM cumulative counter at the last sync
  total_energy_wh  DOUBLE       NOT NULL DEFAULT 0,
  total_spent      DECIMAL(14,6) NOT NULL DEFAULT 0,
  fault            TINYINT(1)   NOT NULL DEFAULT 0,
  theft            TINYINT(1)   NOT NULL DEFAULT 0,
  last_seen        DATETIME     NULL,
  ip               VARCHAR(45)  NULL,
  rssi             INT          NULL,
  CONSTRAINT fk_device_user FOREIGN KEY (active_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- One row per ESP32 sync (every ~2 s). Feeds the Reports charts.
CREATE TABLE IF NOT EXISTS readings (
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
  balance     DECIMAL(14,6) NULL,      -- billed user's balance after this reading
  cost        DECIMAL(14,6) NOT NULL DEFAULT 0,
  fault       TINYINT(1)   NOT NULL DEFAULT 0,
  theft       TINYINT(1)   NOT NULL DEFAULT 0,
  INDEX idx_device_id (device_id, id),
  INDEX idx_created (created_at)
) ENGINE=InnoDB;

-- Recharges and opening balances.
CREATE TABLE IF NOT EXISTS transactions (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  user_id        INT          NOT NULL,
  type           VARCHAR(20)  NOT NULL,   -- recharge | opening
  amount         DECIMAL(14,6) NOT NULL,
  balance_after  DECIMAL(14,6) NOT NULL,
  created_at     DATETIME     NOT NULL,
  CONSTRAINT fk_tx_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Activity log: RFID taps, remote switching, cut-offs, faults, theft alerts.
CREATE TABLE IF NOT EXISTS events (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  device_id   INT          NOT NULL,
  type        VARCHAR(30)  NOT NULL,
  message     VARCHAR(255) NOT NULL,
  rfid_uid    VARCHAR(32)  NULL,
  user_id     INT          NULL,
  created_at  DATETIME     NOT NULL,
  INDEX idx_events_device (device_id, id)
) ENGINE=InnoDB;

-- Key/value settings editable from the Settings page.
CREATE TABLE IF NOT EXISTS settings (
  k  VARCHAR(40)  PRIMARY KEY,
  v  VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

INSERT IGNORE INTO settings (k, v) VALUES
  ('tariff_per_kwh', '8'),      -- Rs per kWh. Use ~950 for a fast classroom demo with a small bulb.
  ('auto_cutoff',    '1'),      -- cut supply when balance reaches 0
  ('low_balance',    '20'),     -- Rs, warning threshold
  ('volt_min',       '180'),    -- V, below this = fault, supply cut
  ('volt_max',       '260'),    -- V, above this = fault, supply cut
  ('theft_current',  '0.010'),  -- A drawn while relay is OFF => theft / bypass alert
  ('poll_ms',        '2000');   -- how often the ESP32 syncs with the server

INSERT IGNORE INTO device_state (id, name) VALUES (1, 'Room A-101');

-- Demo user so the simulator works out of the box (UID DEADBEEF). Replace with your real cards.
INSERT IGNORE INTO users (name, roll_no, room, rfid_uid, balance) VALUES
  ('Demo Student', '000000000', 'A-101', 'DEADBEEF', 100);

