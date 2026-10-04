import os
import re
import pandas as pd
import numpy as np


def print_step(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    print_step("1. Cleaning Orders Table & Handling Date Anomalies")
    
    timestamp_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ]
    for col in timestamp_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            
    df["order_status"] = df["order_status"].astype(str).str.strip().str.lower()
    
    carrier_before_purchase = df["order_delivered_carrier_date"] < df["order_purchase_timestamp"]
    if carrier_before_purchase.sum() > 0:
        print(f"  - Fixed {carrier_before_purchase.sum()} carrier timestamp sequence anomaly rows.")
        df.loc[carrier_before_purchase, "order_delivered_carrier_date"] = np.nan
        
    delivered_before_carrier = (
        df["order_delivered_customer_date"].notnull() & 
        df["order_delivered_carrier_date"].notnull() & 
        (df["order_delivered_customer_date"] < df["order_delivered_carrier_date"])
    )
    if delivered_before_carrier.sum() > 0:
        print(f"  - Detected {delivered_before_carrier.sum()} orders delivered before carrier handover.")
        df.loc[delivered_before_carrier, "order_delivered_carrier_date"] = df.loc[delivered_before_carrier, "order_purchase_timestamp"]

    df["delivery_duration_days"] = (
        df["order_delivered_customer_date"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400.0
    
    neg_duration = df["delivery_duration_days"] < 0
    if neg_duration.sum() > 0:
        print(f"  - Removed {neg_duration.sum()} impossible negative delivery durations.")
        df.loc[neg_duration, "order_delivered_customer_date"] = np.nan
        df.loc[neg_duration, "delivery_duration_days"] = np.nan
        
    extreme_delays = (df["delivery_duration_days"] > 100).sum()
    print(f"  - Extreme delivery outliers (>100 days): {extreme_delays} orders.")
    print(f"Orders cleaned. Total rows: {len(df):,}")
    return df


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    print_step("2. Cleaning Order Items Table & Inspecting Price/Freight")
    
    df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["freight_value"] = pd.to_numeric(df["freight_value"], errors="coerce")
    
    invalid_price = (df["price"] <= 0) | df["price"].isnull()
    if invalid_price.sum() > 0:
        print(f"  - Dropped {invalid_price.sum()} items with invalid <= $0 price.")
        df = df[~invalid_price]
        
    df = df[df["freight_value"] >= 0]
    
    q1_p, q3_p = df["price"].quantile(0.25), df["price"].quantile(0.75)
    iqr_p = q3_p - q1_p
    high_price_thresh = q3_p + 3.0 * iqr_p
    high_price_count = (df["price"] > high_price_thresh).sum()
    
    print(f"  - Price: Min = R${df['price'].min():.2f}, Median = R${df['price'].median():.2f}, Max = R${df['price'].max():.2f}")
    print(f"  - Extreme High-Value items (> R${high_price_thresh:.2f}): {high_price_count:,} items ({high_price_count/len(df)*100:.2f}%)")
    print(f"  - Free shipping items (freight = 0): {(df['freight_value'] == 0).sum():,} items")
    print(f"Order Items cleaned. Total rows: {len(df):,}")
    return df


def clean_payments(df: pd.DataFrame) -> pd.DataFrame:
    print_step("3. Cleaning Payments Table & Resolving Payment Anomalies")
    
    df["payment_type"] = df["payment_type"].astype(str).str.strip().str.lower()
    df["payment_type"] = df["payment_type"].replace({"not_defined": "unknown"})
    df["payment_value"] = pd.to_numeric(df["payment_value"], errors="coerce")
    df["payment_installments"] = pd.to_numeric(df["payment_installments"], errors="coerce")
    
    zero_installments = df["payment_installments"] == 0
    if zero_installments.sum() > 0:
        print(f"  - Fixed {zero_installments.sum()} rows with 0 installments -> converted to 1.")
        df.loc[zero_installments, "payment_installments"] = 1
    df["payment_installments"] = df["payment_installments"].fillna(1).astype(int)
    
    zero_payments = df["payment_value"] <= 0
    if zero_payments.sum() > 0:
        print(f"  - Filtered {zero_payments.sum()} ghost payment records with R$ 0.00 value.")
        df = df[~zero_payments]
        
    print(f"Payments cleaned. Total rows: {len(df):,}")
    return df


def clean_reviews(df: pd.DataFrame, translation_dict_path: str = None) -> pd.DataFrame:
    print_step("4. Cleaning Reviews Table & Translating Comments to English")
    
    for col in ["review_creation_date", "review_answer_timestamp"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        
    df["review_score"] = pd.to_numeric(df["review_score"], errors="coerce")
    df = df[df["review_score"].between(1, 5)]
    
    df["review_comment_title"] = df["review_comment_title"].fillna("").astype(str).str.strip()
    df["review_comment_message"] = df["review_comment_message"].fillna("").astype(str).str.strip()
    
    # Attach English translations if dictionary is available
    if translation_dict_path and os.path.exists(translation_dict_path):
        print(f"  - Loading Portuguese-to-English translation dictionary from:\n    {translation_dict_path}")
        dict_df = pd.read_csv(translation_dict_path)
        trans_map = dict(zip(dict_df["portuguese"], dict_df["english"].fillna("")))
        
        def translate_val(v):
            s = str(v).strip()
            if not s or s in ("nan", "None", ""):
                return ""
            return trans_map.get(s, s)
            
        df["review_comment_title_english"] = df["review_comment_title"].apply(translate_val)
        df["review_comment_message_english"] = df["review_comment_message"].apply(translate_val)
        print("  - Successfully mapped review titles & messages to English.")
    else:
        df["review_comment_title_english"] = df["review_comment_title"]
        df["review_comment_message_english"] = df["review_comment_message"]
        
    before = len(df)
    df = df.drop_duplicates(subset=["review_id", "order_id"]).reset_index(drop=True)
    print(f"  - Deduplicated {before - len(df)} redundant review records.")
    print(f"Reviews cleaned. Total rows: {len(df):,}")
    return df


def clean_products(df_prod: pd.DataFrame, df_trans: pd.DataFrame = None) -> pd.DataFrame:
    print_step("5. Cleaning Products & Imputing 0g Weights / Dimensions")
    
    df_prod["product_category_name"] = df_prod["product_category_name"].fillna("unknown").astype(str).str.strip()
    
    if df_trans is not None and "product_category_name" in df_trans.columns:
        df_prod = df_prod.merge(df_trans, on="product_category_name", how="left")
        df_prod["product_category_name_english"] = df_prod["product_category_name_english"].fillna(
            df_prod["product_category_name"]
        )
        print("  - Product categories translated to English.")
        
    dim_cols = [
        "product_weight_g", "product_length_cm", 
        "product_height_cm", "product_width_cm", "product_photos_qty"
    ]
    for col in dim_cols:
        df_prod[col] = pd.to_numeric(df_prod[col], errors="coerce")
        
    zero_weight = df_prod["product_weight_g"] == 0
    if zero_weight.sum() > 0:
        print(f"  - Found {zero_weight.sum()} products with 0g weight anomaly.")
        df_prod.loc[zero_weight, "product_weight_g"] = np.nan
        
    for col in ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]:
        cat_medians = df_prod.groupby("product_category_name")[col].transform("median")
        global_median = df_prod[col].median()
        df_prod[col] = df_prod[col].fillna(cat_medians).fillna(global_median)
        
    df_prod["product_photos_qty"] = df_prod["product_photos_qty"].fillna(1).astype(int)
    print(f"Products cleaned. Total rows: {len(df_prod):,}")
    return df_prod


def clean_geolocation(df: pd.DataFrame) -> pd.DataFrame:
    print_step("6. Cleaning Geolocation Table (Fixing Coordinates Outside Brazil)")
    
    df["geolocation_lat"] = pd.to_numeric(df["geolocation_lat"], errors="coerce")
    df["geolocation_lng"] = pd.to_numeric(df["geolocation_lng"], errors="coerce")
    
    valid_coords = (
        (df["geolocation_lat"] >= -34.0) & (df["geolocation_lat"] <= 5.5) &
        (df["geolocation_lng"] >= -74.0) & (df["geolocation_lng"] <= -34.0)
    )
    invalid_count = (~valid_coords).sum()
    print(f"  - Found & removed {invalid_count:,} coordinate records outside Brazil boundaries (GPS errors).")
    df = df[valid_coords]
    
    df["geolocation_city"] = df["geolocation_city"].astype(str).str.strip().str.title()
    df["geolocation_state"] = df["geolocation_state"].astype(str).str.strip().str.upper()
    
    df = df.groupby("geolocation_zip_code_prefix").agg({
        "geolocation_lat": "median",
        "geolocation_lng": "median",
        "geolocation_city": "first",
        "geolocation_state": "first"
    }).reset_index()
    
    print(f"Geolocation cleaned & aggregated per zip code. Remaining unique zip codes: {len(df):,}")
    return df


def clean_customers_sellers(df: pd.DataFrame, entity_type: str = "Customer") -> pd.DataFrame:
    print_step(f"7. Cleaning {entity_type} Location Data")
    
    city_col = f"{entity_type.lower()}_city"
    state_col = f"{entity_type.lower()}_state"
    
    df[city_col] = df[city_col].astype(str).str.strip().str.title()
    df[state_col] = df[state_col].astype(str).str.strip().str.upper()
    df = df.drop_duplicates().reset_index(drop=True)
    print(f"{entity_type} data cleaned. Total: {len(df):,}")
    return df


def create_master_orders_dataset(
    df_orders: pd.DataFrame,
    df_items: pd.DataFrame,
    df_payments: pd.DataFrame,
    df_customers: pd.DataFrame,
    df_products: pd.DataFrame,
    df_reviews: pd.DataFrame
) -> pd.DataFrame:
    print_step("8. Building Unified Master Sales Dataset with Review Translations & Flags")
    
    payments_agg = df_payments.groupby("order_id").agg({
        "payment_value": "sum",
        "payment_type": lambda x: ", ".join(sorted(set(x))),
        "payment_installments": "max"
    }).reset_index().rename(columns={"payment_value": "total_payment_value"})
    
    items_agg = df_items.groupby("order_id").agg({
        "order_item_id": "count",
        "price": "sum",
        "freight_value": "sum",
        "product_id": "first"
    }).reset_index().rename(columns={
        "order_item_id": "items_count",
        "price": "total_items_price",
        "freight_value": "total_freight_value"
    })
    
    if "product_category_name_english" in df_products.columns:
        items_agg = items_agg.merge(
            df_products[["product_id", "product_category_name_english"]], 
            on="product_id", 
            how="left"
        )
    
    # Reviews aggregation (including English title & message)
    review_cols = ["order_id", "review_score"]
    for extra_col in ["review_comment_title_english", "review_comment_message_english"]:
        if extra_col in df_reviews.columns:
            review_cols.append(extra_col)
            
    reviews_agg = df_reviews[review_cols].groupby("order_id").first().reset_index()
    
    master = df_orders.merge(df_customers, on="customer_id", how="left")
    master = master.merge(payments_agg, on="order_id", how="left")
    master = master.merge(items_agg, on="order_id", how="left")
    master = master.merge(reviews_agg, on="order_id", how="left")
    
    # Round floats to 2 decimals to ensure clean Power BI imports
    float_cols = ["total_payment_value", "total_items_price", "total_freight_value", "delivery_duration_days", "review_score"]
    for col in float_cols:
        if col in master.columns:
            master[col] = master[col].round(2)
            
    master["is_high_value_order"] = (master["total_payment_value"] > 1000.0).astype(int)
    master["is_delayed_delivery"] = (
        master["order_delivered_customer_date"] > master["order_estimated_delivery_date"]
    ).astype(int)
    master["is_extreme_delivery_delay"] = (master["delivery_duration_days"] > 45.0).astype(int)
    
    print(f"Master Dataset Shape: {master.shape[0]:,} rows, {master.shape[1]} columns")
    return master


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cleaned_data")
    dict_path = os.path.join(data_dir, "review_translation_dictionary.csv")
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n" + "#" * 70)
    print("    EXECUTING OLIST KAGGLE DATA CLEANING & TRANSLATION PIPELINE")
    print("#" * 70)
    
    def load_csv(filename: str):
        path = os.path.join(data_dir, filename)
        if os.path.exists(path):
            print(f"  [LOADING] {filename}...")
            return pd.read_csv(path)
        return None

    df_orders = load_csv("olist_orders_dataset.csv")
    df_items = load_csv("olist_order_items_dataset.csv")
    df_payments = load_csv("olist_order_payments_dataset.csv")
    df_reviews = load_csv("olist_order_reviews_dataset.csv")
    df_products = load_csv("olist_products_dataset.csv")
    df_trans = load_csv("product_category_name_translation.csv")
    df_customers = load_csv("olist_customers_dataset.csv")
    df_sellers = load_csv("olist_sellers_dataset.csv")
    df_geo = load_csv("olist_geolocation_dataset.csv")
    
    df_orders = clean_orders(df_orders)
    df_items = clean_order_items(df_items)
    df_payments = clean_payments(df_payments)
    df_reviews = clean_reviews(df_reviews, dict_path)
    df_products = clean_products(df_products, df_trans)
    df_customers = clean_customers_sellers(df_customers, "Customer")
    df_sellers = clean_customers_sellers(df_sellers, "Seller")
    if df_geo is not None:
        df_geo = clean_geolocation(df_geo)
        df_geo.to_csv(os.path.join(output_dir, "clean_geolocation.csv"), index=False)

    df_orders.to_csv(os.path.join(output_dir, "clean_orders.csv"), index=False)
    df_items.to_csv(os.path.join(output_dir, "clean_order_items.csv"), index=False)
    df_payments.to_csv(os.path.join(output_dir, "clean_payments.csv"), index=False)
    df_reviews.to_csv(os.path.join(output_dir, "clean_reviews.csv"), index=False)
    df_products.to_csv(os.path.join(output_dir, "clean_products.csv"), index=False)
    df_customers.to_csv(os.path.join(output_dir, "clean_customers.csv"), index=False)
    df_sellers.to_csv(os.path.join(output_dir, "clean_sellers.csv"), index=False)
    
if __name__ == "__main__":
    main()
