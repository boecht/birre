#!/usr/bin/env python3
"""Quick live test of company_search_interactive with parent enrichment."""

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

from fastmcp.client import Client
from birre import create_birre_server
from birre.config.settings import resolve_birre_settings
from birre.infrastructure.logging import get_logger


async def test_interactive_search():
    """Test company_search_interactive to verify parent enrichment works."""
    
    api_key = os.getenv("BITSIGHT_API_KEY")
    if not api_key:
        print("❌ BITSIGHT_API_KEY not set")
        return 1
    
    # Set context to risk_manager to enable interactive tools
    os.environ["BIRRE_CONTEXT"] = "risk_manager"
    
    print("🔧 Creating BiRRe server...")
    settings = resolve_birre_settings()
    
    logger = get_logger("birre.test.interactive")
    server = create_birre_server(settings, logger=logger)
    
    async with Client(server) as client:
        print("\n🔍 Testing company_search_interactive with 'GitHub'...")
        
        result = await client.call_tool(
            "company_search_interactive",
            {
                "name": "GitHub",
            }
        )
        
        # Extract result data
        if hasattr(result, 'content') and result.content:
            text = getattr(result.content[0], 'text', None)
            if text:
                data = json.loads(text)
            else:
                data = result.content[0]
        elif hasattr(result, 'data'):
            if hasattr(result.data, 'model_dump'):
                data = result.data.model_dump(mode='json')
            else:
                data = result.data
        else:
            data = result
        
        print(f"\n📊 Result structure: {type(data)}")
        print(f"📊 Keys: {data.keys() if isinstance(data, dict) else 'N/A'}")
        
        if isinstance(data, dict):
            results = data.get('results', [])
            count = data.get('count', 0)
            
            print(f"\n✅ Found {count} results")
            print(f"📝 Results type: {type(results)}")
            
            for i, company in enumerate(results, 1):
                if hasattr(company, 'model_dump'):
                    company = company.model_dump(mode='json')
                
                name = company.get('name', 'Unknown')
                guid = company.get('guid', 'N/A')
                label = company.get('label', 'N/A')
                rating = company.get('rating')
                rating_color = company.get('rating_color')
                
                print(f"\n{'='*60}")
                print(f"Company {i}:")
                print(f"  Label: {label}")
                print(f"  Name: {name}")
                print(f"  GUID: {guid}")
                print(f"  Rating: {rating} ({rating_color})")
                
                # Check if this is a parent entry
                if 'parent of' in label.lower():
                    print(f"  🔗 PARENT ENTRY DETECTED!")
                
                # Show subscription info
                subscription = company.get('subscription', {})
                if hasattr(subscription, 'model_dump'):
                    subscription = subscription.model_dump(mode='json')
                
                if isinstance(subscription, dict):
                    active = subscription.get('active')
                    folders = subscription.get('folders', [])
                    print(f"  Subscribed: {active}")
                    if folders:
                        print(f"  Folders: {', '.join(folders)}")
            
            # Summary
            parent_count = sum(
                1 for r in results 
                if 'parent of' in str(r.get('label', '') if isinstance(r, dict) else getattr(r, 'label', '')).lower()
            )
            
            print(f"\n{'='*60}")
            print(f"📊 SUMMARY:")
            print(f"  Total results: {count}")
            print(f"  Parent entries: {parent_count}")
            print(f"  Search results: {count - parent_count}")
            
            if parent_count > 0:
                print(f"\n✅ SUCCESS: Parent enrichment is working!")
            else:
                print(f"\n⚠️  WARNING: No parent entries found (may be normal if companies have no tree)")
        else:
            print(f"❌ Unexpected data format: {data}")
            return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_interactive_search())
    sys.exit(exit_code)
