-- MySQL Database Setup for Cardiac Post-Care System
-- Run this script in your MySQL database

CREATE DATABASE IF NOT EXISTS post_care_db;
USE post_care_db;

-- Users table (for both patients and doctors)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    user_type ENUM('patient', 'doctor') NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    doctor_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doctor_id) REFERENCES users(id)
);

-- Patient assessments table
CREATE TABLE IF NOT EXISTS patient_assessments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id INT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cardiac_symptoms TEXT,
    breathing_physical TEXT,
    medication_response TEXT,
    activity_fatigue TEXT,
    ai_summary TEXT,
    risk_level ENUM('low', 'medium', 'high') DEFAULT 'medium',
    FOREIGN KEY (patient_id) REFERENCES users(id),
    FOREIGN KEY (doctor_id) REFERENCES users(id)
);

-- Insert sample doctor (optional)
INSERT INTO users (username, email, password_hash, user_type, full_name) 
VALUES ('dr_smith', 'dr.smith@hospital.com', SHA2('doctor123', 256), 'doctor', 'Dr. John Smith');

-- Note: Update the DB_CONFIG in post_care_app_new.py with your MySQL credentials:
-- DB_CONFIG = {
--     'host': 'localhost',
--     'user': 'your_mysql_username',
--     'password': 'your_mysql_password',
--     'database': 'post_care_db'
-- }
