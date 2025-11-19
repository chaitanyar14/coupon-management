from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import date
from enum import Enum

app = FastAPI(title="Coupon Management System")


# ================================
# MODELS
# ================================

class DiscountType(str, Enum):
    FLAT = "FLAT"
    PERCENT = "PERCENT"

class Eligibility(BaseModel):
    allowedUserTiers: Optional[List[str]] = None
    minLifetimeSpend: Optional[float] = None
    minOrdersPlaced: Optional[int] = None
    firstOrderOnly: Optional[bool] = None
    allowedCountries: Optional[List[str]] = None

    minCartValue: Optional[float] = None
    applicableCategories: Optional[List[str]] = None
    excludedCategories: Optional[List[str]] = None
    minItemsCount: Optional[int] = None

class Coupon(BaseModel):
    code: str
    description: Optional[str]
    discountType: DiscountType
    discountValue: float
    maxDiscountAmount: Optional[float]
    startDate: date
    endDate: date
    usageLimitPerUser: Optional[int]
    eligibility: Optional[Eligibility] = None

class UserContext(BaseModel):
    userId: str
    userTier: Optional[str]
    country: Optional[str]
    lifetimeSpend: float = 0
    ordersPlaced: int = 0

class CartItem(BaseModel):
    productId: str
    category: Optional[str]
    unitPrice: float
    quantity: int

class Cart(BaseModel):
    items: List[CartItem]

class BestCouponRequest(BaseModel):
    user: UserContext
    cart: Cart


# ================================
# IN-MEMORY STORAGE
# ================================

coupons: Dict[str, Coupon] = {}
usage_counter: Dict[str, Dict[str, int]] = {}


# ================================
# HELPER FUNCTIONS
# ================================

def cart_total(cart: Cart) -> float:
    return sum(i.unitPrice * i.quantity for i in cart.items)

def eligible(coupon: Coupon, user: UserContext, cart: Cart) -> bool:
    today = date.today()

    # Date validity
    if not (coupon.startDate <= today <= coupon.endDate):
        return False

    e = coupon.eligibility
    if e:

        if e.allowedUserTiers and user.userTier not in e.allowedUserTiers:
            return False

        if e.minLifetimeSpend and user.lifetimeSpend < e.minLifetimeSpend:
            return False

        if e.minOrdersPlaced and user.ordersPlaced < e.minOrdersPlaced:
            return False

        if e.firstOrderOnly and user.ordersPlaced > 0:
            return False

        if e.allowedCountries and user.country not in e.allowedCountries:
            return False

        total = cart_total(cart)
        if e.minCartValue and total < e.minCartValue:
            return False

        categories = {i.category for i in cart.items}

        if e.applicableCategories and not categories.intersection(e.applicableCategories):
            return False

        if e.excludedCategories and categories.intersection(e.excludedCategories):
            return False

        if e.minItemsCount and sum(i.quantity for i in cart.items) < e.minItemsCount:
            return False

    # Usage limit
    if coupon.usageLimitPerUser:
        used = usage_counter.get(coupon.code, {}).get(user.userId, 0)
        if used >= coupon.usageLimitPerUser:
            return False

    return True


def get_discount(coupon: Coupon, total: float) -> float:
    if coupon.discountType == DiscountType.FLAT:
        return coupon.discountValue

    percent = (coupon.discountValue / 100) * total
    if coupon.maxDiscountAmount:
        percent = min(percent, coupon.maxDiscountAmount)

    return percent


# ================================
# ROUTES
# ================================

@app.post("/coupons")
def create_coupon(coupon: Coupon):
    if coupon.code in coupons:
        raise HTTPException(400, "Coupon already exists")

    coupons[coupon.code] = coupon
    usage_counter[coupon.code] = {}

    return {"message": "Coupon created", "coupon": coupon}


@app.get("/coupons")
def list_all():
    return list(coupons.values())


@app.post("/best-coupon")
def best_coupon(req: BestCouponRequest):

    total = cart_total(req.cart)
    best = None
    best_discount = 0

    for c in coupons.values():
        if eligible(c, req.user, req.cart):
            disc = get_discount(c, total)
            if disc > best_discount:
                best = c
                best_discount = disc

    if not best:
        return {"coupon": None}

    return {
        "coupon": best.code,
        "discount": best_discount,
        "final_price": total - best_discount
    }
