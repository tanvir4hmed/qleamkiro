#!/usr/bin/env python3
"""
Phase 1: Migration Script for Existing ChildProfile Records
Adds language_region and trust_score to all existing profiles.
"""
import boto3
import os
import sys
from decimal import Decimal

# Configuration
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
CHILD_PROFILE_TABLE = f"qleam-{ENVIRONMENT}-ChildProfile"

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(CHILD_PROFILE_TABLE)


def migrate_profiles():
    """Add language_region and trust_score to all existing profiles."""
    print(f"Migrating ChildProfile table: {CHILD_PROFILE_TABLE}")
    
    # Scan all profiles
    response = table.scan()
    items = response.get("Items", [])
    
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    
    print(f"Found {len(items)} profiles to migrate")
    
    updated = 0
    skipped = 0
    
    for item in items:
        child_id = item.get("child_id")
        
        # Check if already has new fields
        if "language_region" in item and "trust_score" in item:
            skipped += 1
            continue
        
        # Update with new fields
        try:
            update_expr = "SET "
            expr_values = {}
            
            if "language_region" not in item:
                update_expr += "language_region = :lang, "
                expr_values[":lang"] = "en"  # Default to English
            
            if "trust_score" not in item:
                update_expr += "trust_score = :trust, "
                expr_values[":trust"] = Decimal("0.5")  # Neutral starting score
            
            # Remove trailing comma
            update_expr = update_expr.rstrip(", ")
            
            table.update_item(
                Key={"child_id": child_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
            )
            
            updated += 1
            if updated % 10 == 0:
                print(f"  Updated {updated} profiles...")
        
        except Exception as e:
            print(f"  Error updating {child_id}: {e}")
    
    print(f"\nMigration complete:")
    print(f"  Updated: {updated}")
    print(f"  Skipped (already migrated): {skipped}")
    print(f"  Total: {len(items)}")


if __name__ == "__main__":
    migrate_profiles()
