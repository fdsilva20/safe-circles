"""Open data: the public, anonymised live figures the UNICEF Venture Fund asks for."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import render
from app.services.metrics import summary

router = APIRouter()


@router.get("/data")
def data_page(request: Request, db: Session = Depends(get_db)):
    return render(request, "data.html", m=summary(db))


@router.get("/data.json")
def data_json(db: Session = Depends(get_db)):
    return summary(db)
