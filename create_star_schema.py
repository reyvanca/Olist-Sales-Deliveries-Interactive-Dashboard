"""
=============================================================================
         STAR SCHEMA DATA WAREHOUSE GENERATOR (Olist E-Commerce)
=============================================================================
Creates Kimball Star Schema Dimension & Fact Tables from Cleaned Olist Data:
 1. dim_customer
 2. dim_product
 3. dim_seller
 4. dim_date
 5. dim_order_status
 6. fact_orders (Order-level measures)
 7. fact_order_items (Item-level sales transaction measures)
=============================================================================
"""

import os
import pandas as pd
import numpy as np


def print_step(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def generate_dim_date(start_date="2016-01-01", end_date="2018-12-31") -> pd.DataFrame:
    """Generates a complete Calendar Date Dimension table."""
    print_step("1. Generating Date Dimension (dim_date)")
    
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    df_date = pd.DataFrame({"full_date": dates})
    
    df_date["date_key"] = df_date["full_date"].dt.strftime("%Y%m%d").astype(int)
    df_date["year"] = df_date["full_date"].dt.year
    df_date["quarter"] = df_date["full_date"].dt.quarter
    df_date["quarter_name"] = "Q" + df_date["quarter"].astype(str)
    df_date["month"] = df_date["full_date"].dt.month
    df_date["month_name"] = df_date["full_date"].dt.strftime("%B")
    df_date["month_year"] = df_date["full_date"].dt.strftime("%b %Y")
    df_date["day"] = df_date["full_date"].dt.day
    df_date["day_of_week"] = df_date["full_date"].dt.dayofweek + 1
    df_date["day_name"] = df_date["full_date"].dt.strftime("%A")
    df_date["is_weekend"] = df_date["day_of_week"].isin([6, 7]).astype(int)
    
    print(f"dim_date created: {len(df_date):,} rows (From {start_date} to {end_date})")
    return df_date


def generate_dim_customer(df_customers: pd.DataFrame) -> pd.DataFrame:
    """Generates Customer Dimension table."""
    print_step("2. Generating Customer Dimension (dim_customer)")
    
    df_cust = df_customers.copy()
    
    # Region Mapping based on Brazilian States
    region_map = {
        "SP": "Southeast", "RJ": "Southeast", "MG": "Southeast", "ES": "Southeast",
        "PR": "South", "RS": "South", "SC": "South",
        "BA": "Northeast", "PE": "Northeast", "CE": "Northeast", "MA": "Northeast",
        "PB": "Northeast", "RN": "Northeast", "AL": "Northeast", "SE": "Northeast", "PI": "Northeast",
        "GO": "Central-West", "DF": "Central-West", "MT": "Central-West", "MS": "Central-West",
        "PA": "North", "AM": "North", "RO": "North", "AC": "North", "AP": "North", "TO": "North", "RR": "North"
    }
    
    df_cust["customer_region"] = df_cust["customer_state"].map(region_map).fillna("Other")
    print(f"dim_customer created: {len(df_cust):,} unique customers")
    return df_cust


def generate_dim_product(df_products: pd.DataFrame) -> pd.DataFrame:
    """Generates Product Dimension table with weight category categorization."""
    print_step("3. Generating Product Dimension (dim_product)")
    
    df_prod = df_products.copy()
    
    # Categorize product weight
    def get_weight_cat(w):
        if pd.isna(w): return "Unknown"
        if w < 500: return "Light (<500g)"
        if w < 2000: return "Medium (500g-2kg)"
        if w < 10000: return "Heavy (2kg-10kg)"
        return "Very Heavy (>10kg)"
        
    df_prod["weight_category"] = df_prod["product_weight_g"].apply(get_weight_cat)
    print(f"dim_product created: {len(df_prod):,} unique products")
    return df_prod


def generate_dim_seller(df_sellers: pd.DataFrame) -> pd.DataFrame:
    """Generates Seller Dimension table."""
    print_step("4. Generating Seller Dimension (dim_seller)")
    
    df_seller = df_sellers.copy()
    region_map = {
        "SP": "Southeast", "RJ": "Southeast", "MG": "Southeast", "ES": "Southeast",
        "PR": "South", "RS": "South", "SC": "South",
        "BA": "Northeast", "PE": "Northeast", "CE": "Northeast", "MA": "Northeast",
        "PB": "Northeast", "RN": "Northeast", "AL": "Northeast", "SE": "Northeast", "PI": "Northeast",
        "GO": "Central-West", "DF": "Central-West", "MT": "Central-West", "MS": "Central-West",
        "PA": "North", "AM": "North", "RO": "North", "AC": "North", "AP": "North", "TO": "North", "RR": "North"
    }
    df_seller["seller_region"] = df_seller["seller_state"].map(region_map).fillna("Other")
    print(f"dim_seller created: {len(df_seller):,} unique sellers")
    return df_seller


def generate_fact_orders(
    df_orders: pd.DataFrame, 
    df_payments: pd.DataFrame, 
    df_items: pd.DataFrame, 
    df_reviews: pd.DataFrame
) -> pd.DataFrame:
    """Generates Order-level Fact Table (fact_orders)."""
    print_step("5. Generating Fact Table: Order Level (fact_orders)")
    
    # 1. Aggregate payments per order
    pay_agg = df_payments.groupby("order_id").agg({
        "payment_value": "sum",
        "payment_type": lambda x: ", ".join(sorted(set(x))),
        "payment_installments": "max"
    }).reset_index().rename(columns={"payment_value": "total_payment_value"})
    
    # 2. Aggregate items per order
    items_agg = df_items.groupby("order_id").agg({
        "order_item_id": "count",
        "price": "sum",
        "freight_value": "sum"
    }).reset_index().rename(columns={
        "order_item_id": "items_count",
        "price": "total_items_price",
        "freight_value": "total_freight_value"
    })
    
    # 3. Reviews aggregation
    reviews_agg = df_reviews.groupby("order_id").agg({
        "review_score": "mean"
    }).reset_index()
    
    # Merge into fact_orders
    fact_orders = df_orders.merge(pay_agg, on="order_id", how="left")
    fact_orders = fact_orders.merge(items_agg, on="order_id", how="left")
    fact_orders = fact_orders.merge(reviews_agg, on="order_id", how="left")
    
    # Create Date Keys (Foreign Keys linking to dim_date)
    fact_orders["order_purchase_date_key"] = (
        pd.to_datetime(fact_orders["order_purchase_timestamp"]).dt.strftime("%Y%m%d").fillna(-1).astype(int)
    )
    fact_orders["order_delivered_date_key"] = (
        pd.to_datetime(fact_orders["order_delivered_customer_date"]).dt.strftime("%Y%m%d").fillna(-1).astype(int)
    )
    fact_orders["order_estimated_date_key"] = (
        pd.to_datetime(fact_orders["order_estimated_delivery_date"]).dt.strftime("%Y%m%d").fillna(-1).astype(int)
    )
    
    # Derived Business Measures
    fact_orders["total_payment_value"] = fact_orders["total_payment_value"].round(2)
    fact_orders["total_items_price"] = fact_orders["total_items_price"].round(2)
    fact_orders["total_freight_value"] = fact_orders["total_freight_value"].round(2)
    fact_orders["delivery_duration_days"] = fact_orders["delivery_duration_days"].round(2)
    
    # Delivery delay measure (positive = late, negative = early)
    fact_orders["delivery_delay_days"] = (
        (pd.to_datetime(fact_orders["order_delivered_customer_date"]) - 
         pd.to_datetime(fact_orders["order_estimated_delivery_date"])).dt.total_seconds() / 86400.0
    ).round(2)
    
    fact_orders["is_delayed"] = (fact_orders["delivery_delay_days"] > 0).astype(int)
    
    # Select Fact Columns
    cols = [
        "order_id", "customer_id", 
        "order_purchase_date_key", "order_delivered_date_key", "order_estimated_date_key",
        "order_status", "payment_type", "payment_installments",
        "items_count", "total_items_price", "total_freight_value", "total_payment_value",
        "delivery_duration_days", "delivery_delay_days", "is_delayed", "review_score"
    ]
    fact_orders = fact_orders[cols]
    print(f"fact_orders created: {len(fact_orders):,} orders")
    return fact_orders


def generate_fact_order_items(df_items: pd.DataFrame, df_orders: pd.DataFrame) -> pd.DataFrame:
    """Generates Item-Transaction Fact Table (fact_order_items)."""
    print_step("6. Generating Fact Table: Order Items (fact_order_items)")
    
    fact_items = df_items.merge(
        df_orders[["order_id", "customer_id", "order_purchase_timestamp"]], 
        on="order_id", 
        how="left"
    )
    
    fact_items["order_purchase_date_key"] = (
        pd.to_datetime(fact_items["order_purchase_timestamp"]).dt.strftime("%Y%m%d").fillna(-1).astype(int)
    )
    
    fact_items["price"] = fact_items["price"].round(2)
    fact_items["freight_value"] = fact_items["freight_value"].round(2)
    fact_items["total_item_cost"] = (fact_items["price"] + fact_items["freight_value"]).round(2)
    
    cols = [
        "order_id", "order_item_id", "customer_id", "product_id", "seller_id",
        "order_purchase_date_key", "price", "freight_value", "total_item_cost"
    ]
    fact_items = fact_items[cols]
    print(f"fact_order_items created: {len(fact_items):,} order items")
    return fact_items


def main():
    cleaned_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cleaned_data")
    star_schema_dir = os.path.join(cleaned_dir, "star_schema")
    os.makedirs(star_schema_dir, exist_ok=True)
    
    print("\n" + "#" * 70)
    print("      BUILDING KIMBALL STAR SCHEMA DATA WAREHOUSE TABLES")
    print("#" * 70)
    
    # Load Clean Data
    df_customers = pd.read_csv(os.path.join(cleaned_dir, "clean_customers.csv"))
    df_products = pd.read_csv(os.path.join(cleaned_dir, "clean_products.csv"))
    df_sellers = pd.read_csv(os.path.join(cleaned_dir, "clean_sellers.csv"))
    df_orders = pd.read_csv(os.path.join(cleaned_dir, "clean_orders.csv"))
    df_items = pd.read_csv(os.path.join(cleaned_dir, "clean_order_items.csv"))
    df_payments = pd.read_csv(os.path.join(cleaned_dir, "clean_payments.csv"))
    df_reviews = pd.read_csv(os.path.join(cleaned_dir, "clean_reviews.csv"))
    
    # Generate Dimensions
    dim_date = generate_dim_date("2016-01-01", "2018-12-31")
    dim_customer = generate_dim_customer(df_customers)
    dim_product = generate_dim_product(df_products)
    dim_seller = generate_dim_seller(df_sellers)
    
    # Generate Facts
    fact_orders = generate_fact_orders(df_orders, df_payments, df_items, df_reviews)
    fact_order_items = generate_fact_order_items(df_items, df_orders)
    
    # Save as Individual CSV files in star_schema/
    print_step("7. Exporting Star Schema Tables to CSV")
    tables = {
        "dim_date": dim_date,
        "dim_customer": dim_customer,
        "dim_product": dim_product,
        "dim_seller": dim_seller,
        "fact_orders": fact_orders,
        "fact_order_items": fact_order_items
    }
    
    for name, df in tables.items():
        path = os.path.join(star_schema_dir, f"{name}.csv")
        df.to_csv(path, index=False)
        print(f"  [CSV EXPORTED] {name}.csv ({len(df):,} rows)")
        
    # Save as Multi-Sheet Excel Data Warehouse
    print_step("8. Exporting Unified Star Schema Excel Data Warehouse")
    excel_path = os.path.join(cleaned_dir, "olist_star_schema_dw.xlsx")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        dim_date.to_excel(writer, index=False, sheet_name="dim_date")
        dim_customer.to_excel(writer, index=False, sheet_name="dim_customer")
        dim_product.to_excel(writer, index=False, sheet_name="dim_product")
        dim_seller.to_excel(writer, index=False, sheet_name="dim_seller")
        fact_orders.to_excel(writer, index=False, sheet_name="fact_orders")
        
    print(f"  [EXCEL EXPORTED] {excel_path}")
    print("\n" + "#" * 70)
    print("      STAR SCHEMA DATA WAREHOUSE GENERATED SUCCESSFULLY!")
    print("#" * 70 + "\n")


if __name__ == "__main__":
    main()
