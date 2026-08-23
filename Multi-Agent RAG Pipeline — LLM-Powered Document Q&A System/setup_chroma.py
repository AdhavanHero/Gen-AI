"""
Populates a local Chroma vector database with domain knowledge used by the
RAG Retriever component in the Langflow pipeline.

Run this ONCE before using the app: python scripts/setup_chroma.py
This creates a ./chroma_db folder (gitignored) that the flow reads from.
"""
import chromadb
import os

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "chroma_db")

client = chromadb.PersistentClient(path=CHROMA_PATH)


def get_or_create(name):
    try:
        return client.get_collection(name)
    except Exception:
        return client.create_collection(name)


# ---------------- Healthcare ----------------
healthcare_collection = get_or_create("healthcare_knowledge")
healthcare_docs = [
    "Healthcare datasets typically contain patient_id, age, diagnosis, treatment, outcome, and cost columns.",
    "Key metrics: readmission rate, treatment effectiveness, average length of stay, cost per diagnosis.",
    "Risk factors to flag: high age combined with high comorbidity count, unusually long length of stay, high treatment cost outliers.",
    "Readmission within 30 days is a critical quality signal — flag patients and diagnoses with high readmission rates.",
    "Treatment effectiveness should be compared by grouping outcome against treatment type and diagnosis.",
]
healthcare_collection.add(ids=[f"health_{i}" for i in range(len(healthcare_docs))], documents=healthcare_docs)

# ---------------- Finance ----------------
finance_collection = get_or_create("finance_knowledge")
finance_docs = [
    "Finance datasets typically contain transaction_id, account_id, amount, merchant, category, and date columns.",
    "Key metrics: fraud probability, transaction anomaly score, spending pattern by category, account risk level.",
    "Fraud red flags: sudden amount spikes relative to account history, unknown or unusual merchants, odd-hour transactions, geographic anomalies.",
    "Use IQR or z-score based outlier detection on transaction amount grouped by account_id to catch anomalies.",
    "Portfolio-level analysis should look at diversification across categories and concentration risk.",
]
finance_collection.add(ids=[f"finance_{i}" for i in range(len(finance_docs))], documents=finance_docs)

# ---------------- Supply Chain ----------------
supply_chain_collection = get_or_create("supply_chain_knowledge")
supply_chain_docs = [
    "Supply chain datasets typically contain product, warehouse/district, quantity, supplier, and date columns.",
    "Key metrics: stockout frequency, lead time variability, inventory turnover, reorder point breaches.",
    "Stockout risk increases when quantity_dispensed regularly exceeds opening_stock plus quantity_received.",
    "Long lead_time_days combined with high stockout_flag rate indicates a supplier bottleneck worth flagging.",
    "Recommend safety stock levels based on historical maximum dispensed quantity plus a buffer for lead time.",
]
supply_chain_collection.add(ids=[f"supply_{i}" for i in range(len(supply_chain_docs))], documents=supply_chain_docs)

# ---------------- Retail ----------------
retail_collection = get_or_create("retail_knowledge")
retail_docs = [
    "Retail datasets typically contain customer_id, order_id, purchase_date, amount, category, and payment_method columns.",
    "Key metrics: RFM score (Recency, Frequency, Monetary), customer lifetime value, churn risk, category preference.",
    "Segment customers into high-value (top monetary + frequent), at-risk (long recency gap), and new customers.",
    "Churn risk increases sharply when a customer's days-since-last-purchase exceeds 2x their historical average gap.",
    "Category-level analysis should highlight which product categories drive the most revenue per customer segment.",
]
retail_collection.add(ids=[f"retail_{i}" for i in range(len(retail_docs))], documents=retail_docs)

print("Chroma collections populated successfully!")
print("Collections created: healthcare_knowledge, finance_knowledge, supply_chain_knowledge, retail_knowledge")
print(f"Stored at: {CHROMA_PATH}")
