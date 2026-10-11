# ShopSphere Analytics - Streamlit Frontend

A clean, interactive Streamlit frontend for the **ShopSphere Analytics** project.

## 🌟 Features

- **KPI Cards:** Total Revenue, Total Orders, Average Order Value (AOV), and Active Customers with growth deltas.
- **Visual Charts:**
  - Daily Revenue & Order volume trends.
  - Category breakdown (Electronics, Fashion, Home, Beauty, Sports).
- **Customer Directory & Table:**
  - Searchable and filterable by region (North, South, East, West) and customer segment (VIP, Regular, New, At-Risk).
  - One-click CSV export button.
- **Natural Language Question Input Box:**
  - Interactive input box with pre-configured suggestion chips to query key metrics and customer churn insights.

---

## 🚀 How to Run

1. Open your terminal in the `Hcl-hackathon-Gitboosters` directory.
2. Install frontend requirements:
   ```bash
   pip install -r frontend/requirements.txt
   ```
3. Launch the Streamlit dashboard:
   ```bash
   streamlit run frontend/app.py
   ```
4. The dashboard will automatically open in your default browser at `http://localhost:8501`.

---

## 🌿 Git Instructions (Branch: `vikrant`)

To commit this frontend to your `vikrant` branch:

```bash
git checkout vikrant
git add frontend/
git commit -m "Add ShopSphere Analytics Streamlit frontend"
git push origin vikrant
```
