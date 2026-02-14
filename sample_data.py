"""
Sample Data Generator
Generates synthetic transaction data for testing feature store
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random


def generate_sample_transactions(n_users: int = 100, n_transactions: int = 1000) -> pd.DataFrame:
    """
    Generate synthetic transaction data
    
    Args:
        n_users: Number of unique users
        n_transactions: Total number of transactions
    
    Returns:
        DataFrame with transaction data
    """
    np.random.seed(42)
    random.seed(42)
    
    merchant_categories = [
        'groceries', 'restaurants', 'gas_stations', 'retail', 
        'entertainment', 'utilities', 'healthcare', 'travel',
        'online_shopping', 'subscriptions'
    ]
    
    # Generate user IDs
    user_ids = [f"user_{i:05d}" for i in range(n_users)]
    
    transactions = []
    
    for i in range(n_transactions):
        # Random user
        user_id = random.choice(user_ids)
        
        # Transaction details
        transaction = {
            'transaction_id': f"txn_{i:08d}",
            'user_id': user_id,
            'amount': round(np.random.lognormal(mean=3.5, sigma=1.2), 2),  # Realistic transaction amounts
            'merchant_category': random.choice(merchant_categories),
            'timestamp': datetime.now() - timedelta(
                days=random.randint(0, 90),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )
        }
        
        transactions.append(transaction)
    
    df = pd.DataFrame(transactions)
    
    # Ensure amount is positive and reasonable
    df['amount'] = df['amount'].clip(lower=0.01, upper=10000)
    
    return df


if __name__ == "__main__":
    # Generate and save sample data
    print("🎲 Generating sample transaction data...")
    
    transactions = generate_sample_transactions(n_users=1000, n_transactions=10000)
    
    print(f"✅ Generated {len(transactions)} transactions for {transactions['user_id'].nunique()} users")
    print("\nSample data:")
    print(transactions.head(10))
    print("\nSummary statistics:")
    print(transactions.describe())
    
    # Save to CSV
    from pathlib import Path
    output_dir = Path("./data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "transactions.csv"
    transactions.to_csv(output_file, index=False)
    print(f"\n💾 Saved to {output_file}")
