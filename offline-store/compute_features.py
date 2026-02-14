"""
Offline Feature Computation
Computes features in batch and stores to Parquet files
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def compute_user_features(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute aggregated user features from transactions
    
    Args:
        transactions_df: DataFrame with columns [user_id, transaction_id, amount, timestamp, 
merchant_category]
    
    Returns:
        DataFrame with user-level features
    """
    logger.info(f"Computing features for {transactions_df['user_id'].nunique()} users...")
    
    # Aggregate features per user
    user_features = transactions_df.groupby('user_id').agg({
        'amount': ['count', 'sum', 'mean', 'std', 'max', 'min'],
        'transaction_id': 'count',
        'merchant_category': lambda x: x.mode()[0] if len(x) > 0 else 'unknown'
    }).reset_index()
    
    # Flatten column names
    user_features.columns = ['_'.join(col).strip('_') if col[1] else col[0] 
                             for col in user_features.columns.values]
    
    # Rename columns to be more meaningful
    user_features = user_features.rename(columns={
        'amount_count': 'total_transactions',
        'amount_sum': 'total_spend',
        'amount_mean': 'avg_transaction_amount',
        'amount_std': 'transaction_amount_std',
        'amount_max': 'max_transaction',
        'amount_min': 'min_transaction',
        'merchant_category': 'favorite_category'
    })
    
    # Add time-based features
    transactions_df['timestamp'] = pd.to_datetime(transactions_df['timestamp'])
    latest_txn = transactions_df.groupby('user_id')['timestamp'].max().reset_index()
    latest_txn.columns = ['user_id', 'last_transaction_date']
    
    user_features = user_features.merge(latest_txn, on='user_id')
    
    # Days since last transaction
    now = datetime.now()
    user_features['days_since_last_transaction'] = (
        now - pd.to_datetime(user_features['last_transaction_date'])
    ).dt.days
    
    # Transaction frequency (transactions per day)
    first_txn = transactions_df.groupby('user_id')['timestamp'].min().reset_index()
    first_txn.columns = ['user_id', 'first_transaction_date']
    
    user_features = user_features.merge(first_txn, on='user_id')
    
    user_features['customer_lifetime_days'] = (
        pd.to_datetime(user_features['last_transaction_date']) - 
        pd.to_datetime(user_features['first_transaction_date'])
    ).dt.days + 1
    
    user_features['transaction_frequency'] = (
        user_features['total_transactions'] / user_features['customer_lifetime_days']
    )
    
    # Risk score (simple heuristic)
    user_features['risk_score'] = (
        (user_features['max_transaction'] / user_features['avg_transaction_amount'].clip(lower=1)) * 
        (user_features['transaction_frequency'] * 10)
    ).fillna(0).clip(upper=100)
    
    # Drop intermediate columns
    user_features = user_features.drop(columns=[
        'first_transaction_date',
        'last_transaction_date',
        'transaction_id_count'
    ])
    
    # Fill NaN values
    user_features = user_features.fillna(0)
    
    logger.info(f"✅ Computed {len(user_features.columns) - 1} features for {len(user_features)} users")
    
    return user_features


def save_features_to_parquet(features_df: pd.DataFrame, output_dir: Path, entity_type: str, version: str = 
"v1"):
    """Save features to Parquet file with partitioning"""
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Add metadata
    features_df['_feature_version'] = version
    features_df['_computed_at'] = datetime.utcnow().isoformat()
    
    # Save to Parquet
    filename = f"{entity_type}_{version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
    filepath = output_dir / filename
    
    features_df.to_parquet(
        filepath,
        engine='pyarrow',
        compression='snappy',
        index=False
    )
    
    logger.info(f"✅ Saved features to {filepath}")
    logger.info(f"   Size: {filepath.stat().st_size / 1024:.2f} KB")
    
    return filepath


def load_features_from_parquet(filepath: Path) -> pd.DataFrame:
    """Load features from Parquet file"""
    df = pd.read_parquet(filepath)
    logger.info(f"✅ Loaded {len(df)} records with {len(df.columns)} columns")
    return df


if __name__ == "__main__":
    # Example usage
    from examples.sample_data import generate_sample_transactions
    
    # Generate sample data
    transactions = generate_sample_transactions(n_users=1000, n_transactions=10000)
    
    # Compute features
    user_features = compute_user_features(transactions)
    
    # Save to Parquet
    output_path = save_features_to_parquet(
        user_features,
        output_dir=Path("./data/offline-features"),
        entity_type="user",
        version="v1"
    )
    
    # Verify
    print("\nSample features:")
    print(user_features.head())
    print("\nFeature columns:")
    print(user_features.columns.tolist())
