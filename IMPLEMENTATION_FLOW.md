# Company Search Interactive - Complete Implementation Flow

**Status:** 🚧 In Development  
**Date:** 2025-10-30  
**Purpose:** Risk manager enriched search with ratings, hierarchy, and subscription status

---

## Business Requirements

The risk manager needs:
1. ✅ **Company list** - from search results
2. ✅ **Parent companies** - all parents up to root from company tree
3. ✅ **Rating** (number + color) - from getCompany
4. ✅ **Subscription status + folders** - from getFolders + search results

---

## Complete Data Flow

### **Step 1: Search with Portfolio Check**

**API Call:**
```python
companySearch(
    name="...",           # or domain="..."
    expand="details.in_portfolio"
)
```

**Returns:**
```json
{
  "results": [
    {
      "guid": "xxx",
      "name": "Company Name",
      "primary_domain": "example.com",
      "description": "...",
      "website": "...",
      "details": {
        "in_portfolio": true/false  // ← Key field!
      }
    }
  ]
}
```

**Extract:**
- List of company candidates
- Which ones need ephemeral subscriptions (`in_portfolio == false`)

---

### **Step 2: Bulk Subscribe to Non-Portfolio Companies**

**Logic:**
```python
non_subscribed_guids = [
    candidate["guid"] 
    for candidate in candidates 
    if not candidate.get("details", {}).get("in_portfolio", False)
]
```

**API Call:**
```python
manageSubscriptionsBulk(
    action="add",
    guids=non_subscribed_guids,
    folder=default_folder,
    subscription_type=default_subscription_type
)
```

**Track:**
- `ephemeral_subscriptions`: Set of GUIDs we just subscribed to
- These will be unsubscribed in Step 6

---

### **Step 3a: Get Company Details + Rating**

**For each search result:**

**API Call:**
```python
getCompany(
    guid=company_guid,
    fields="guid,name,description,ipv4_count,primary_domain,has_company_tree,current_rating"
)
```

**Returns:**
```json
{
  "guid": "xxx",
  "name": "Company Name",
  "description": "...",
  "ipv4_count": 12345,
  "primary_domain": "example.com",
  "has_company_tree": true/false,  // ← Check this!
  "current_rating": 700             // ← Rating number
}
```

**Store:**
- Company details including `current_rating`
- Flag `has_company_tree` for next step

---

### **Step 3b: Get Company Tree (if exists)**

**Logic:**
```python
if company_details.get("has_company_tree"):
    tree = getCompaniesTree(company_guid)
```

**API Call:**
```python
getCompaniesTree(guid=company_guid)
```

**Returns:**
```json
{
  "guid": "root-guid",
  "name": "Root Company",
  "rating": 580,
  "is_subscribed": true,
  "children": [
    {
      "guid": "parent-guid",
      "name": "Parent Company",
      "rating": 630,
      "is_subscribed": true,
      "children": [
        {
          "guid": "our-company-guid",  // ← Find this!
          "name": "Our Company",
          "rating": 700,
          "is_subscribed": true,
          "children": []
        }
      ]
    }
  ]
}
```

**Extract:**
- Find path from root to our company
- Collect **all parent GUIDs** (from immediate parent to root)
- Example: If tree is `Root → Parent → OurCompany`, parents are: `[Parent, Root]`

---

### **Step 3c: Enrich with Parent Companies**

**For each parent GUID found in Step 3b:**

1. **Check if parent is already in search results:**
   ```python
   if parent_guid in search_results_guids:
       # Use existing data, skip API calls
       continue
   ```

2. **Check if parent needs subscription:**
   ```python
   # We already know from tree's "is_subscribed" field
   if not parent_is_subscribed:
       # Subscribe to parent
       manageSubscriptionsBulk(action="add", guids=[parent_guid])
       ephemeral_subscriptions.add(parent_guid)  # Track for cleanup
   ```

3. **Get parent company details:**
   ```python
   parent_details = getCompany(
       guid=parent_guid,
       fields="guid,name,description,primary_domain,current_rating"
   )
   ```

4. **Add parent to results:**
   ```python
   results.append({
       "label": f"Parent of {original_company_name}",
       "guid": parent_guid,
       "name": parent_details["name"],
       "rating": parent_details["current_rating"],
       "is_parent_entry": True,
       # ... other fields
   })
   ```

---

### **Step 4: Get Folder Memberships**

**API Call (once for all companies):**
```python
folders = getFolders()
```

**Returns:**
```json
[
  {
    "guid": "folder-guid",
    "name": "Folder Name",
    "companies": ["company-guid-1", "company-guid-2", ...]
  }
]
```

**Build mapping:**
```python
folder_memberships = {
    "company-guid-1": ["Folder A", "Folder B"],
    "company-guid-2": ["Folder C"],
    # ...
}
```

---

### **Step 5: Build Subscription Snapshots**

**For each company (including parents):**

```python
subscription = {
    "active": company_guid in folder_memberships or originally_subscribed,
    "subscription_type": subscription_type if subscribed else None,
    "folders": folder_memberships.get(company_guid, []),
    "subscription_end_date": None  # Would come from getCompany if needed
}
```

---

### **Step 6: Bulk Unsubscribe Ephemeral Subscriptions**

**Cleanup all ephemeral subscriptions at once:**

```python
if ephemeral_subscriptions:
    manageSubscriptionsBulk(
        action="delete",
        guids=list(ephemeral_subscriptions)
    )
```

**Includes:**
- Original search results that weren't subscribed (from Step 2)
- Parent companies we subscribed to (from Step 3c)

**Excludes:**
- Companies that were already subscribed before we started
- We track this via the `ephemeral_subscriptions` set

---

## Output Model

```python
class CompanyInteractiveResult(BaseModel):
    label: str                              # "Company Name (guid)" or "Parent of X"
    guid: str                               # Company GUID
    name: str                               # Company name
    primary_domain: str                     # Primary domain
    website: str                            # Website URL
    description: str                        # Company description
    employee_count: int | None = None       # From search expand (if available)
    rating: int | None = None               # From getCompany (current_rating)
    rating_color: str | None = None         # Derived from rating number
    parent_company: str | None = None       # Parent company name (for original entries)
    parent_guid: str | None = None          # Parent company GUID (for original entries)
    is_parent_entry: bool = False           # True for parent entries added to results
    child_of: str | None = None             # Original company name (for parent entries)
    subscription: SubscriptionSnapshot
```

---

## Rating Color Mapping

**✅ FOUND:** Use existing `_rating_color` helper from `company_rating/service.py`:

```python
from birre.domain.company_rating.service import _rating_color

def _rating_color(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 740:
        return "green"
    if value >= 630:
        return "yellow"
    return "red"
```

**Thresholds:**
- **Green:** 740-900
- **Yellow:** 630-739
- **Red:** 250-629
- **None:** if rating is None

---

## API Call Estimation

For **5 search results**:
- 1 × companySearch (with expand)
- 1 × manageSubscriptionsBulk (subscribe non-portfolio)
- 5 × getCompany (for search results)
- ~3 × getCompaniesTree (if has_company_tree)
- ~6 × getCompany (for parent companies not in results)
- 1 × manageSubscriptionsBulk (subscribe parents)
- 1 × getFolders (get folder memberships)
- 1 × manageSubscriptionsBulk (cleanup ephemeral)

**Total: ~18 API calls** for 5 results with trees

For **100 API calls budget**: Can handle ~25 search results with complex trees.

**This is acceptable for risk manager use case** - quality over speed.

---

## Implementation Checklist

### Phase 1: Search & Subscribe
- [ ] Update `_build_company_search_params` to include `expand="details.in_portfolio"`
- [ ] Update `_build_candidate` to extract `in_portfolio` flag
- [ ] Create `_identify_non_subscribed_companies` helper
- [ ] Create `_bulk_subscribe_companies` helper
- [ ] Track ephemeral subscriptions in a set

### Phase 2: Company Details & Rating
- [ ] Keep existing `_fetch_company_details` but update fields param
- [ ] Add `current_rating` to fields list
- [ ] Add `has_company_tree` to fields list
- [ ] Find and import rating color helper

### Phase 3: Company Tree & Parents
- [ ] Create `_fetch_company_tree` helper
- [ ] Create `_find_parent_path_in_tree` helper (recursive tree walk)
- [ ] Create `_extract_parent_guids` helper
- [ ] Create `_enrich_with_parent_companies` helper
- [ ] Subscribe to parents if needed (track in ephemeral set)
- [ ] Call getCompany for parent details
- [ ] Add parents to results with special label

### Phase 4: Folders & Cleanup
- [ ] Keep existing `_fetch_folder_memberships`
- [ ] Update `_build_subscription_snapshot` to use new data
- [ ] Create `_cleanup_ephemeral_subscriptions` helper
- [ ] Bulk unsubscribe at end

### Phase 5: Response Building
- [ ] Update `CompanyInteractiveResult` model with new fields
- [ ] Update `_format_result_entry` to include rating + color
- [ ] Update `_format_result_entry` to include parent info
- [ ] Create `_format_parent_entry` for parent companies
- [ ] Update response assembly logic

### Phase 6: Testing
- [ ] Test with company that has no tree
- [ ] Test with company that has simple tree (1 parent)
- [ ] Test with company that has complex tree (multiple levels)
- [ ] Test with mix of subscribed/non-subscribed
- [ ] Test parent deduplication (parent already in search results)
- [ ] Verify ephemeral cleanup happens correctly
- [ ] Update selftest validation to handle new fields

---

## Notes

- **No reverting**: Build on top of current implementation
- **Ephemeral subscriptions**: Now justified for risk manager use case
- **Performance**: Quality over speed - acceptable for human-in-the-loop workflow
- **Parent hierarchy**: Show ALL parents up to root, not just immediate parent
- **Cleanup**: Single bulk unsubscribe at end (more efficient)
- **Tree traversal**: Company can only be in ONE tree (confirmed by user)

---

## Next Steps

1. ✅ Document complete flow (this file)
2. ✅ Find rating color helper in codebase (`_rating_color` from `company_rating/service.py`)
3. ⏳ Implement Phase 1 (Search & Subscribe)
4. ⏳ Implement Phase 2 (Company Details & Rating)
5. ⏳ Implement Phase 3 (Company Tree & Parents)
6. ⏳ Implement Phase 4 (Folders & Cleanup)
7. ⏳ Implement Phase 5 (Response Building)
8. ⏳ Implement Phase 6 (Testing)

---

**Last Updated:** 2025-10-30  
**Status:** Flow documented, ready for implementation
