from datetime import date, datetime, timedelta
from itertools import count
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders, restocking_orders, tasks

# Monotonic id sources: ids are never reused after a delete
task_ids = count(1)
purchase_order_ids = count(len(purchase_orders) + 1)

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: Optional[float] = None
    lead_time_days: Optional[int] = None

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False
    purchase_order_id: Optional[str] = None

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0)
    unit_cost: float = Field(gt=0)
    expected_delivery_date: date
    notes: Optional[str] = Field(default=None, max_length=1000)

TaskPriority = Literal["high", "medium", "low"]

class Task(BaseModel):
    id: str
    title: str
    priority: TaskPriority
    # camelCase to match the task objects the client already uses
    dueDate: str
    status: Literal["pending", "completed"]

class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    priority: TaskPriority = "medium"
    dueDate: date

class RestockingItem(BaseModel):
    sku: str
    name: str
    trend: str
    current_demand: int
    forecasted_demand: int
    demand_gap: int
    quantity: int
    unit_cost: float
    line_total: float
    lead_time_days: int

class RestockingRecommendations(BaseModel):
    budget: float
    items: List[RestockingItem]
    total_cost: float
    remaining_budget: float
    max_lead_time_days: int
    full_cost: float

class RestockingOrderLine(BaseModel):
    sku: str
    quantity: int = Field(gt=0)

class CreateRestockingOrderRequest(BaseModel):
    budget: float = Field(ge=0)
    items: List[RestockingOrderLine] = Field(min_length=1)

class RestockingOrder(BaseModel):
    id: str
    order_number: str
    status: str
    submitted_at: str
    expected_delivery: str
    lead_time_days: int
    budget: float
    total_value: float
    items: List[RestockingItem]

def build_recommendations(budget: float) -> dict:
    """Pick forecast items to restock within the budget (greedy by demand gap)."""
    candidates = []
    for forecast in demand_forecasts:
        gap = forecast["forecasted_demand"] - forecast["current_demand"]
        # Only items with growing demand and a known price can be restocked
        if gap <= 0 or forecast.get("unit_cost") is None:
            continue
        candidates.append({
            "sku": forecast["item_sku"],
            "name": forecast["item_name"],
            "trend": forecast["trend"],
            "current_demand": forecast["current_demand"],
            "forecasted_demand": forecast["forecasted_demand"],
            "demand_gap": gap,
            "quantity": gap,
            "unit_cost": forecast["unit_cost"],
            "line_total": round(gap * forecast["unit_cost"], 2),
            "lead_time_days": forecast.get("lead_time_days") or 0,
        })

    # Biggest gaps first; cheaper line wins a tie so the order is deterministic
    candidates.sort(key=lambda c: (-c["demand_gap"], c["line_total"]))

    selected = []
    remaining = budget
    for candidate in candidates:
        # Skip (not stop) when an item doesn't fit, so cheaper items further
        # down the ranking can still use the leftover budget
        if candidate["line_total"] <= remaining:
            selected.append(candidate)
            remaining = round(remaining - candidate["line_total"], 2)

    return {
        "budget": budget,
        "items": selected,
        "total_cost": round(sum(i["line_total"] for i in selected), 2),
        "remaining_budget": round(remaining, 2),
        "max_lead_time_days": max((i["lead_time_days"] for i in selected), default=0),
        # Cost of funding every positive gap; the client uses it as the slider max
        "full_cost": round(sum(c["line_total"] for c in candidates), 2),
    }

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Attach the PO (if any) so the dashboard keeps "View PO" after a reload
        po = find_purchase_order(item["id"])
        item_dict["has_purchase_order"] = po is not None
        item_dict["purchase_order_id"] = po["id"] if po else None
        result.append(item_dict)
    return result

def find_purchase_order(backlog_item_id: str) -> Optional[dict]:
    """Return the purchase order raised for a backlog item, if any"""
    return next((po for po in purchase_orders if po["backlog_item_id"] == backlog_item_id), None)

@app.post("/api/purchase-orders", response_model=PurchaseOrder, status_code=201)
def create_purchase_order(request: CreatePurchaseOrderRequest):
    """Raise a purchase order for a backlog item (one PO per item)"""
    if not any(b["id"] == request.backlog_item_id for b in backlog_items):
        raise HTTPException(status_code=404, detail=f"Backlog item {request.backlog_item_id} not found")
    if find_purchase_order(request.backlog_item_id):
        raise HTTPException(status_code=409, detail=f"Backlog item {request.backlog_item_id} already has a purchase order")

    po = {
        "id": f"PO-{next(purchase_order_ids):04d}",
        "backlog_item_id": request.backlog_item_id,
        "supplier_name": request.supplier_name.strip(),
        "quantity": request.quantity,
        "unit_cost": request.unit_cost,
        "expected_delivery_date": request.expected_delivery_date.isoformat(),
        "status": "Pending",
        "created_date": datetime.now().replace(microsecond=0).isoformat(),
        "notes": request.notes,
    }
    purchase_orders.append(po)
    return po

@app.get("/api/purchase-orders/{backlog_item_id}", response_model=PurchaseOrder)
def get_purchase_order_by_backlog_item(backlog_item_id: str):
    """Get the purchase order raised for a backlog item"""
    po = find_purchase_order(backlog_item_id)
    if not po:
        raise HTTPException(status_code=404, detail=f"No purchase order for backlog item {backlog_item_id}")
    return po

@app.get("/api/tasks", response_model=List[Task])
def get_tasks():
    """Get tasks created through the API, newest first"""
    return list(reversed(tasks))

@app.post("/api/tasks", response_model=Task, status_code=201)
def create_task(request: CreateTaskRequest):
    """Create a pending task"""
    # "api-" prefix keeps these ids apart from the client's built-in mock tasks (1, 2, 3...)
    task = {
        "id": f"api-{next(task_ids)}",
        "title": request.title.strip(),
        "priority": request.priority,
        "dueDate": request.dueDate.isoformat(),
        "status": "pending",
    }
    tasks.append(task)
    return task

def find_task(task_id: str) -> dict:
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task

@app.delete("/api/tasks/{task_id}", response_model=Task)
def delete_task(task_id: str):
    """Delete a task and return it"""
    task = find_task(task_id)
    tasks.remove(task)
    return task

@app.patch("/api/tasks/{task_id}", response_model=Task)
def toggle_task(task_id: str):
    """Toggle a task between pending and completed"""
    task = find_task(task_id)
    task["status"] = "completed" if task["status"] == "pending" else "pending"
    return task

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

@app.get("/api/restocking/recommendations", response_model=RestockingRecommendations)
def get_restocking_recommendations(budget: float = Query(..., ge=0)):
    """Recommend forecasted items to restock within the given budget"""
    return build_recommendations(budget)

@app.post("/api/restocking/orders", response_model=RestockingOrder, status_code=201)
def create_restocking_order(request: CreateRestockingOrderRequest):
    """Submit a restocking order. Prices and lead times come from server data, never the client."""
    forecasts_by_sku = {f["item_sku"]: f for f in demand_forecasts}

    lines = []
    for line in request.items:
        forecast = forecasts_by_sku.get(line.sku)
        if not forecast or forecast.get("unit_cost") is None:
            raise HTTPException(status_code=400, detail=f"Unknown or unpriced SKU: {line.sku}")
        lines.append({
            "sku": line.sku,
            "name": forecast["item_name"],
            "trend": forecast["trend"],
            "current_demand": forecast["current_demand"],
            "forecasted_demand": forecast["forecasted_demand"],
            "demand_gap": forecast["forecasted_demand"] - forecast["current_demand"],
            "quantity": line.quantity,
            "unit_cost": forecast["unit_cost"],
            "line_total": round(line.quantity * forecast["unit_cost"], 2),
            "lead_time_days": forecast.get("lead_time_days") or 0,
        })

    total_value = round(sum(l["line_total"] for l in lines), 2)
    if total_value > request.budget:
        raise HTTPException(
            status_code=400,
            detail=f"Order total {total_value} exceeds budget {request.budget}"
        )

    # The order arrives once its slowest item arrives
    lead_time_days = max(l["lead_time_days"] for l in lines)
    submitted_at = datetime.now().replace(microsecond=0)
    sequence = len(restocking_orders) + 1

    order = {
        "id": str(sequence),
        "order_number": f"RST-{submitted_at.year}-{sequence:04d}",
        "status": "Submitted",
        "submitted_at": submitted_at.isoformat(),
        "expected_delivery": (submitted_at + timedelta(days=lead_time_days)).isoformat(),
        "lead_time_days": lead_time_days,
        "budget": request.budget,
        "total_value": total_value,
        "items": lines,
    }
    restocking_orders.append(order)
    return order

@app.get("/api/restocking/orders", response_model=List[RestockingOrder])
def get_restocking_orders():
    """Get submitted restocking orders, newest first"""
    return list(reversed(restocking_orders))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
