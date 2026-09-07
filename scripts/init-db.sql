-- BlockyDNS Hub Database Initialization Schema for MySQL / MariaDB
CREATE DATABASE IF NOT EXISTS blocky_logs CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE blocky_logs;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    last_login DATETIME
) ENGINE=InnoDB;

-- 2. Devices Table
CREATE TABLE IF NOT EXISTS devices (
    client_ip VARCHAR(45) PRIMARY KEY,
    hostname VARCHAR(255),
    friendly_name VARCHAR(255),
    icon VARCHAR(50) DEFAULT 'device',
    group_name VARCHAR(50) DEFAULT 'default',
    first_seen DATETIME,
    last_seen DATETIME,
    total_queries INT DEFAULT 0,
    blocked_queries INT DEFAULT 0
) ENGINE=InnoDB;

-- 3. Blocklists Table
CREATE TABLE IF NOT EXISTS blocklists (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(500) UNIQUE NOT NULL,
    category VARCHAR(100) DEFAULT 'Adware & Tracking',
    enabled TINYINT(1) DEFAULT 1,
    rule_count INT DEFAULT 0,
    last_updated DATETIME
) ENGINE=InnoDB;

-- 4. Custom Rules Table
CREATE TABLE IF NOT EXISTS custom_rules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rule_type ENUM('whitelist', 'blacklist') NOT NULL,
    domain VARCHAR(255) NOT NULL,
    is_wildcard TINYINT(1) DEFAULT 0,
    is_regex TINYINT(1) DEFAULT 0,
    enabled TINYINT(1) DEFAULT 1,
    comment VARCHAR(255),
    created_at DATETIME NOT NULL
) ENGINE=InnoDB;

-- 5. Local DNS Table
CREATE TABLE IF NOT EXISTS local_dns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    domain VARCHAR(255) UNIQUE NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    record_type VARCHAR(10) DEFAULT 'A',
    is_wildcard TINYINT(1) DEFAULT 0,
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME NOT NULL
) ENGINE=InnoDB;

-- 6. Domain Routing Table (Geo-Bypass)
CREATE TABLE IF NOT EXISTS domain_routing (
    id INT AUTO_INCREMENT PRIMARY KEY,
    domain_pattern VARCHAR(255) UNIQUE NOT NULL,
    resolver VARCHAR(255) NOT NULL,
    tag VARCHAR(100) DEFAULT 'Geo-Bypass',
    enabled TINYINT(1) DEFAULT 1,
    created_at DATETIME NOT NULL
) ENGINE=InnoDB;

-- 7. Upstreams Table
CREATE TABLE IF NOT EXISTS upstreams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    endpoint VARCHAR(255) UNIQUE NOT NULL,
    protocol VARCHAR(20) NOT NULL,
    enabled TINYINT(1) DEFAULT 1,
    is_custom TINYINT(1) DEFAULT 0,
    last_latency_ms FLOAT DEFAULT 0.0
) ENGINE=InnoDB;

-- 8. Blocky GORM log_entries Table
CREATE TABLE IF NOT EXISTS log_entries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_ts DATETIME NOT NULL,
    client_ip VARCHAR(45),
    client_name VARCHAR(255),
    duration_ms INT DEFAULT 0,
    reason VARCHAR(255),
    response_type VARCHAR(50),
    question_name VARCHAR(255),
    question_type VARCHAR(20),
    answer TEXT,
    response_code VARCHAR(20),
    effective_tldp VARCHAR(100),
    hostname VARCHAR(255),
    question VARCHAR(255),
    INDEX idx_log_ts (request_ts),
    INDEX idx_log_ip (client_ip),
    INDEX idx_log_type (response_type),
    INDEX idx_log_qname (question_name),
    INDEX idx_log_question (question)
) ENGINE=InnoDB;

-- 9. Settings Table
CREATE TABLE IF NOT EXISTS settings (
    `key` VARCHAR(100) PRIMARY KEY,
    `value` TEXT NOT NULL
) ENGINE=InnoDB;

-- 10. Blocked Services Table (1-Click App Blocker)
CREATE TABLE IF NOT EXISTS blocked_services (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(100) NOT NULL,
    icon VARCHAR(20) NOT NULL,
    domains_json TEXT NOT NULL,
    enabled TINYINT(1) DEFAULT 0,
    updated_at DATETIME NOT NULL,
    INDEX idx_blocked_services_cat (category, enabled)
) ENGINE=InnoDB;

