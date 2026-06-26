# Intern Onboarding: Returns Database Analysis

Welcome to the team! We are excited to have you on board. Your primary project will involve diving into our **Returns Database**, which is hosted on Supabase. Your goal is to explore this data, uncover trends, and provide us with actionable insights regarding why products are being returned.

This guide will help you get set up and outline the initial analysis tasks.

---

## 1. Accessing the Data

Our database is hosted on **Supabase** (a PostgreSQL database platform). 

**Your Credentials:**
*   **Host:** `[Insert Supabase Host URL]`
*   **Database Name:** `postgres`
*   **Port:** `5432`
*   **Username:** `[Insert Intern Username]`
*   **Password:** `[Insert Password]`

*Note: Please reach out to your manager if you do not have these credentials yet.*

---

## 2. Choose Your Tools

You have the flexibility to approach this analysis using the tools you are most comfortable with. Since you are in your 3rd year, this is a great opportunity to practice industry-standard tools. We recommend picking one of the following paths:

### Option A: SQL (Recommended for Data Extraction & Quick Stats)
You can connect directly to the Supabase database using a SQL client like **DBeaver**, **DataGrip**, or even through the **Supabase Dashboard** online.
*   **Pros:** Direct access, very fast for aggregating data.

### Option B: Python (Recommended for Deep Analysis & Visualizations)
You can use Python with libraries like `pandas`, `sqlalchemy`, and `matplotlib`/`seaborn`. You can work in a **Jupyter Notebook**.
*   **Pros:** Great for complex data manipulation, charting, and saving your workflow.

### AI Assistance is Encouraged!
We highly encourage you to use AI-assisted coding platforms to help you learn and write code faster. Feel free to use tools like:
*   **ChatGPT** or **Claude** (for asking "How do I write a SQL query to find..." or "Help me debug this pandas code")
*   **Cursor** or **GitHub Copilot** (if you are coding in an IDE like VS Code)

*Tip: When asking AI for help, always provide it with the names of the tables and columns you are working with so it can write accurate code for you!*

---

## 3. The Dataset

Once you connect to the database, you will likely see a table named something like `returns` or `returned_orders`. 

*(Manager Note: Update the schema below to match your actual database)*
Here are some of the key columns you will be working with:
*   `order_id`: The original ID of the purchase.
*   `product_id`: The ID of the item returned.
*   `return_date`: When the return was processed.
*   `return_reason`: Why the customer returned the item (e.g., "Defective", "Wrong Size", "Changed Mind").
*   `refund_amount`: The dollar amount refunded.
*   `customer_id`: The ID of the customer who made the return.

---

## 4. Your Tasks: Exploratory Data Analysis (EDA)

Here is a list of descriptive statistics and analyses we would like you to pull. Start simple and work your way down the list!

### Level 1: Basic Descriptive Statistics
1.  **Total Volume:** How many total returns were processed in the dataset?
2.  **Financial Impact:** What is the total `refund_amount` across all returns? What is the *average* refund amount per return?
3.  **Missing Data Check:** Are there any columns with a lot of missing (NULL) values that we should be aware of?

### Level 2: Categorical Analysis
4.  **Top Reasons:** What are the top 3 most common `return_reason`s? What percentage of total returns does each represent?
5.  **Problem Products:** Which 5 `product_id`s have the highest *number* of returns? 
6.  **Serial Returners:** Are there specific `customer_id`s that return items frequently? Find the top 10 customers with the most returns.

### Level 3: Time-Series Trends
7.  **Monthly Trends:** Group the returns by month (using `return_date`). Which month had the highest number of returns? 
8.  **Day of Week:** Are returns more likely to be processed on certain days of the week?

---

## 5. Deliverables

Once you have completed the analysis, please prepare a brief summary of your findings. You can present this as:
*   A short presentation (slides) with some charts.
*   A clean Jupyter Notebook with your code and markdown cells explaining your insights.
*   A written summary document.

Don't hesitate to ask questions if you get stuck or if the data looks weird. Data analysis is often about investigating anomalies! Good luck!
