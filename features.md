# Feature Documentation — Text-to-SQL ERP Assistant

**Project:** Text-to-SQL ERP Integration Tool  
**Internship Period:** Summer 2026  
**Model Backend:** Google Gemini Flash (Low Latency, High Intelligence)  
**Target Domain:** Manufacturing ERP (Material Management, Accounts, Sales Cohorts)

---

## 1. Overview

The **Text-to-SQL ERP Assistant** is an intelligent natural language interface that allows users to query complex ERP databases using plain English. Powered by **Google Gemini Flash**, the tool translates user questions into optimized SQL queries, executes them against the connected ERP database, and presents results in an intuitive, conversational format. The system is designed for manufacturing companies with multi-department ERP setups, ensuring secure, role-based data access with minimal latency.

---

## 2. Core Features

### 2.1 Authentication & User Management
- **Secure Login:** Users authenticate via username and password credentials configured by the admin.
- **Admin-Controlled Access:** Only administrators have the privilege to create new user accounts, preventing unauthorized access and product misuse.
- **Role-Based Data Access:** Multiple predefined roles (Material Management, Accounts, Sales Cohorts) restrict data visibility. A single user can be assigned multiple roles, enabling cross-department flexibility while maintaining strict data boundaries.

### 2.2 Conversational Chat Interface
- **Familiar UX:** A clean, Claude-like chat interface provides users with an intuitive, modern experience — no learning curve required.
- **Natural Language Input:** Users type questions in plain English (e.g., *"Show me total material consumption for Q2 2026"*) and receive instant SQL-generated responses.

### 2.3 Contextual Follow-Up Support
- **Multi-Turn Conversations:** Users can ask follow-up questions without restating the full context. The system retains memory of the **last 3 messages** to maintain conversational continuity.
- **Iterative Refinement:** If the initial response is not satisfactory, users can refine their query naturally (e.g., *"Filter that by department B only"*), and the system adapts intelligently.

### 2.4 Chat History
- **Persistent Sessions:** All chat conversations are automatically saved and accessible via the history panel.
- **Quick Reference:** Users can revisit previous queries and results at any time, improving productivity and auditability.

### 2.5 Auto Analysis & Visual Analysis
Two powerful sidebar toggles enhance raw SQL result interpretation:

| Mode | Description |
|------|-------------|
| **Auto Analysis** | Summarizes large result sets into concise, human-readable insights — highlighting key metrics, trends, and anomalies without manual scanning of hundreds of rows. |
| **Visual Analysis** | Generates stunning, AI-powered data visualizations (charts, graphs) from tabular results. Includes AI-drawn insights and interpretations directly from the visualization, making complex data instantly actionable. |

Both modes can be toggled **on/off dynamically** based on user preference.

---

## 3. Admin Settings (Admin-Only Access)

A dedicated settings page restricted to admin accounts, comprising three core modules:

### 3.1 User Settings
- Create and manage new user accounts.
- Assign usernames, passwords, and role permissions.

### 3.2 Database Configuration
- **Multi-Database Support:** Admins can configure and store multiple database connection strings.
- **Dynamic Switching:** Users can change the active database mid-session **without page reload**, enabling seamless cross-database querying.
- **Flexible Access Mapping:** Admins can grant a single user access to multiple databases, making the tool adaptable for organizations operating across several ERP instances.

### 3.3 Application Logs
- **Global Message Monitoring:** Displays all queries submitted by all users across the platform.
- **Audit & Oversight:** Enables admins to monitor application usage, detect anomalies, and ensure compliance.

---

## 4. ERP Coverage

The tool is built to interface with the following ERP modules for manufacturing companies:

| Module | Use Cases |
|--------|-----------|
| **Material Management** | Inventory tracking, stock levels, procurement status, material consumption reports |
| **Accounts** | Financial summaries, ledger queries, expense tracking, revenue analysis |
| **Sales Cohorts** | Sales performance by cohort, revenue trends, customer segmentation, deal pipelines |

---

## 5. Key Value Propositions

- **Zero SQL Knowledge Required:** Business users interact with ERP data using natural language.
- **Low Latency Responses:** Gemini Flash ensures near-instant query generation and execution.
- **Enterprise-Grade Security:** Admin-controlled access, role-based permissions, and full query logging.
- **Multi-Database Flexibility:** Seamless switching across ERP databases without disrupting workflow.
- **Intelligent Data Presentation:** Auto summaries and visualizations transform raw data into actionable insights.

---

*Document Version: 1.0 | Last Updated: July 2026*
