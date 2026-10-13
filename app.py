
import os
import sqlite3
from datetime import date, datetime

import gradio as gr
import pandas as pd

DB_NAME = "finance.db"


# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_date TEXT NOT NULL,
            txn_type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT UNIQUE NOT NULL,
            amount REAL NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def get_transactions():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(
        "SELECT * FROM transactions ORDER BY txn_date DESC, id DESC",
        conn
    )
    conn.close()
    return df


def get_budgets():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(
        "SELECT category, amount FROM budgets ORDER BY category",
        conn
    )
    conn.close()
    return df


# ---------- DASHBOARD ----------   

def dashboard():
    df = get_transactions()
    current_month = date.today().strftime("%Y-%m")

    if df.empty:
        summary = (
            f"### Monthly Summary ({date.today():%B %Y})\n"
            "- **Income:** ₹0.00\n"
            "- **Expenses:** ₹0.00\n"
            "- **Balance:** ₹0.00"
        )
        return 0.0, 0.0, 0.0, summary, df

    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["txn_type"] = df["txn_type"].astype(str).str.strip().str.lower()

    def fix_date(value):
        try:
            number = float(value)
            # Unix timestamps may be in seconds or milliseconds
            if number > 1e12:
                number /= 1000
            if number > 1e9:
                return datetime.fromtimestamp(number).strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError, OSError):
            pass

        try:
            return pd.to_datetime(value).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return ""

    df["fixed_date"] = df["txn_date"].apply(fix_date)
    monthly = df[df["fixed_date"].str.startswith(current_month)]

    income = monthly.loc[monthly["txn_type"] == "income", "amount"].sum()
    expenses = monthly.loc[monthly["txn_type"] == "expense", "amount"].sum()
    balance = income - expenses

    summary = (
        f"### Monthly Summary ({date.today():%B %Y})\n"
        f"- **Income:** ₹{income:,.2f}\n"
        f"- **Expenses:** ₹{expenses:,.2f}\n"
        f"- **Balance:** ₹{balance:,.2f}"
    )

    return float(income), float(expenses), float(balance), summary, df


# ---------- ADD TRANSACTION ----------
def add_transaction(txn_date, txn_type, category, amount, description):
    if not category or not category.strip():
        return "Please enter a category.", *dashboard()

    try:
        amount = float(amount)
        if amount <= 0:
            return "Amount must be greater than zero.", *dashboard()
    except (TypeError, ValueError):
        return "Enter a valid amount.", *dashboard()

    if not txn_date:
        return "Please select a date.", *dashboard()

    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        INSERT INTO transactions
        (txn_date, txn_type, category, amount, description)
        VALUES (?, ?, ?, ?, ?)
    """, (
        str(txn_date),
        txn_type.lower(),
        category.strip(),
        amount,
        (description or "").strip()
    ))
    conn.commit()
    conn.close()

    income, expenses, balance, summary, df = dashboard()
    return "Transaction added successfully!", income, expenses, balance, summary, df


# ---------- DELETE TRANSACTION ----------
def delete_transaction(transaction_id):
    if transaction_id is None:
        return "Enter a transaction ID.", *dashboard()

    try:
        transaction_id = int(transaction_id)
    except (TypeError, ValueError):
        return "Enter a valid transaction ID.", *dashboard()

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()

    income, expenses, balance, summary, df = dashboard()

    message = (
        "Transaction deleted successfully."
        if deleted
        else "Transaction ID not found."
    )
    return message, income, expenses, balance, summary, df


# ---------- BUDGET ----------
def save_budget(category, amount):
    if not category or not category.strip():
        return "Please enter a budget category.", get_budgets()

    try:
        amount = float(amount)
        if amount <= 0:
            return "Budget must be greater than zero.", get_budgets()
    except (TypeError, ValueError):
        return "Enter a valid budget amount.", get_budgets()

    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        INSERT INTO budgets (category, amount)
        VALUES (?, ?)
        ON CONFLICT(category) DO UPDATE SET amount = excluded.amount
    """, (category.strip(), amount))
    conn.commit()
    conn.close()

    return "Budget saved successfully!", get_budgets()


def budget_report():
    budgets = get_budgets()
    transactions = get_transactions()

    if budgets.empty:
        return pd.DataFrame(
            columns=["Category", "Budget", "Spent", "Remaining", "Status"]
        )

    current_month = date.today().strftime("%Y-%m")

    if not transactions.empty:
        transactions["amount"] = pd.to_numeric(
            transactions["amount"], errors="coerce"
        ).fillna(0)
        transactions["txn_type"] = (
            transactions["txn_type"].astype(str).str.strip().str.lower()
        )
        transactions["txn_date"] = transactions["txn_date"].astype(str)

        spent = transactions[
            (transactions["txn_type"] == "expense")
            & transactions["txn_date"].str.startswith(current_month)
        ]

        spent = spent.groupby("category")["amount"].sum().to_dict()
    else:
        spent = {}

    rows = []

    for _, budget in budgets.iterrows():
        category = budget["category"]
        limit = float(budget["amount"])
        total_spent = float(spent.get(category, 0))
        remaining = limit - total_spent

        rows.append({
            "Category": category,
            "Budget": limit,
            "Spent": total_spent,
            "Remaining": remaining,
            "Status": "Over budget" if remaining < 0 else "Within budget"
        })

    return pd.DataFrame(rows)


# ---------- REFRESH ----------
def refresh_all():
    income, expenses, balance, summary, transactions = dashboard()
    budgets = get_budgets()
    report = budget_report()

    return income, expenses, balance, summary, transactions, budgets, report


# ---------- USER INTERFACE ----------
init_db()


finance_css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

.gradio-container {
    max-width: 1200px !important;
    margin: auto !important;
    font-family: 'Inter', sans-serif !important;
    background: #f5f7fc !important;
}

.gradio-container .main {
    background: #f5f7fc !important;
}

#finance-header {
    background: linear-gradient(120deg, #111a3b, #4436a8);
    padding: 30px;
    border-radius: 22px;
    color: white;
    margin-bottom: 22px;
    box-shadow: 0 12px 30px rgba(39, 42, 100, 0.18);
}

#finance-header h1 {
    color: white !important;
    font-size: 30px !important;
    font-weight: 800 !important;
    margin-bottom: 8px;
}

#finance-header p {
    color: #e0e7ff !important;
    font-size: 14px;
}

#summary-cards {
    gap: 16px;
    margin: 18px 0;
}

.metric-card {
    background: white;
    border: 1px solid #e7eaf4;
    border-radius: 18px;
    padding: 20px !important;
    box-shadow: 0 5px 18px rgba(30, 41, 80, 0.05);
}

.metric-card label {
    color: #667085 !important;
    font-weight: 600 !important;
}

.metric-card input {
    font-size: 25px !important;
    font-weight: 800 !important;
    color: #202b55 !important;
    background: transparent !important;
    border: none !important;
    padding-left: 0 !important;
}

.tabs {
    border: none !important;
}

.tab-nav {
    gap: 8px !important;
    border-bottom: 1px solid #e1e6f0 !important;
    margin-bottom: 20px !important;
}

.tab-nav button {
    border-radius: 12px 12px 0 0 !important;
    font-weight: 600 !important;
    padding: 13px 18px !important;
}

button.primary {
    background: linear-gradient(120deg, #5546d7, #7967f8) !important;
    border: none !important;
    border-radius: 12px !important;
    color: white !important;
    font-weight: 700 !important;
    min-height: 45px;
}

button.primary:hover {
    filter: brightness(1.06);
}

button {
    border-radius: 10px !important;
}

input, textarea, select {
    border-radius: 10px !important;
}

.block {
    border-radius: 16px !important;
}

.dataframe {
    border-radius: 12px !important;
    overflow: hidden !important;
}

footer {
    visibility: hidden;
}

@media (max-width: 700px) {
    .gradio-container {
        padding: 12px !important;
    }

    #finance-header {
        padding: 22px;
    }

    #finance-header h1 {
        font-size: 23px !important;
    }
}
"""

with gr.Blocks(
    title="Personal Finance Tracker",
    theme=gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="slate",
        neutral_hue="slate"
    ),
    css=finance_css
) as app:
    gr.Markdown("""
    # 💰 Personal Finance & Daily Expense Tracker

    Track your income, expenses, monthly balance, and budgets in one place.
    """)

    with gr.Tab("Dashboard"):
        with gr.Row():
            income_card = gr.Number(label="Monthly Income (₹)", value=0)
            expense_card = gr.Number(label="Monthly Expenses (₹)", value=0)
            balance_card = gr.Number(label="Monthly Balance (₹)", value=0)

        summary_box = gr.Markdown()
        transaction_table = gr.Dataframe(
            label="All Transactions",
            interactive=False
        )
        refresh_button = gr.Button("Refresh Dashboard")

        refresh_button.click(
            fn=dashboard,
            outputs=[
                income_card,
                expense_card,
                balance_card,
                summary_box,
                transaction_table
            ]
        )

    with gr.Tab("Add Transaction"):
        txn_date = gr.DateTime(
            label="Transaction Date",
            include_time=False,
            value=datetime.now()
        )
        txn_type = gr.Dropdown(
            choices=["Income", "Expense"],
            value="Expense",
            label="Transaction Type"
        )
        category = gr.Textbox(
            label="Category",
            placeholder="e.g. Salary, Food, Travel"
        )
        amount = gr.Number(label="Amount (₹)", minimum=0)
        description = gr.Textbox(
            label="Description",
            placeholder="Optional notes"
        )
        add_button = gr.Button("Add Transaction", variant="primary")
        add_message = gr.Markdown()

        add_button.click(
            fn=add_transaction,
            inputs=[txn_date, txn_type, category, amount, description],
            outputs=[
                add_message,
                income_card,
                expense_card,
                balance_card,
                summary_box,
                transaction_table
            ]
        )

    with gr.Tab("Delete Transaction"):
        delete_id = gr.Number(
            label="Transaction ID",
            precision=0
        )
        delete_button = gr.Button("Delete Transaction")
        delete_message = gr.Markdown()

        delete_button.click(
            fn=delete_transaction,
            inputs=[delete_id],
            outputs=[
                delete_message,
                income_card,
                expense_card,
                balance_card,
                summary_box,
                transaction_table
            ]
        )

    with gr.Tab("Budgets"):
        gr.Markdown(
            "### Set a monthly budget for each category. "
            "Saving an existing category updates its budget."
        )

        budget_category = gr.Textbox(
            label="Category",
            placeholder="e.g. Food"
        )
        budget_amount = gr.Number(label="Monthly Budget (₹)", minimum=0)
        budget_button = gr.Button("Save Budget", variant="primary")
        budget_message = gr.Markdown()

        budgets_table = gr.Dataframe(
            label="Saved Budgets",
            interactive=False
        )
        report_table = gr.Dataframe(
            label="Monthly Budget Report",
            interactive=False
        )
        budget_refresh = gr.Button("Refresh Budgets")

        budget_button.click(
            fn=save_budget,
            inputs=[budget_category, budget_amount],
            outputs=[budget_message, budgets_table]
        )

        budget_refresh.click(
            fn=refresh_all,
            outputs=[
                income_card,
                expense_card,
                balance_card,
                summary_box,
                transaction_table,
                budgets_table,
                report_table
            ]
        )

    app.load(
        fn=refresh_all,
        outputs=[
            income_card,
            expense_card,
            balance_card,
            summary_box,
            transaction_table,
            budgets_table,
            report_table
        ]
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)
