import os
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime, timedelta

try:
    import certifi
    ca_file = certifi.where()
except ImportError:
    ca_file = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mongodb_client")

# URI de conexión a MongoDB Atlas
DEFAULT_MONGO_URI = "mongodb+srv://faridzemanate_db_user:BnmNXRFB8RJ8RVZy@cluster0.kavgcce.mongodb.net/analytics_db?retryWrites=true&w=majority"
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or DEFAULT_MONGO_URI

class MongoDBClient:
    def __init__(self, uri: str = None):
        self.uri = uri or MONGO_URI
        self.client = None
        self.db = None
        self.collection = None
        try:
            # Manejo de conexiones con pool, retry y soporte SSL (certifi)
            client_kwargs = {
                "maxPoolSize": 50,
                "minPoolSize": 5,
                "retryWrites": True,
                "serverSelectionTimeoutMS": 5000,
                "connectTimeoutMS": 5000
            }
            if ca_file:
                client_kwargs["tlsCAFile"] = ca_file

            self.client = MongoClient(self.uri, **client_kwargs)
            # Ping para verificar conexión inmediata con el clúster
            self.client.admin.command("ping")
            self.db = self.client["analytics_db"]
            self.collection = self.db["logs"]
            
            # Creación de índices solicitados en el taller
            self.collection.create_index("timestamp")
            self.collection.create_index("user_id")
            self.collection.create_index("event_type")
            logger.info("Conectado exitosamente a MongoDB Atlas y creados los índices.")
        except ConnectionFailure as e:
            logger.error(f"Error de conexión a MongoDB: {e}")
        except Exception as e:
            logger.error(f"Error inicializando MongoDB: {e}")

    def get_recent_metrics(self):
        """Query de analytics para últimas 24 horas"""
        if self.collection is None:
            return []
        time_threshold = datetime.utcnow() - timedelta(days=1)
        results = list(self.collection.find({"timestamp": {"$gte": time_threshold}}))
        # Formatear ObjectId y datetime para serialización JSON limpia
        for r in results:
            if "_id" in r:
                r["_id"] = str(r["_id"])
            if isinstance(r.get("timestamp"), datetime):
                r["timestamp"] = r["timestamp"].isoformat()
        return results

    def is_connected(self) -> bool:
        """Verifica salud de la conexión"""
        if not self.client:
            return False
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def log_event(self, event_type: str, data: dict, user_id: str = None, space_id: int = None) -> str:
        """Registra un evento analítico en la colección logs"""
        if self.collection is None:
            self.__init__()
            if self.collection is None:
                raise ConnectionError("MongoDB Atlas no está disponible.")

        doc = {
            "event_type": event_type,
            "data": data,
            "user_id": user_id or data.get("user_email") or data.get("user_id"),
            "space_id": space_id or data.get("space_id"),
            "timestamp": datetime.utcnow()
        }
        res = self.collection.insert_one(doc)
        return str(res.inserted_id)

    def get_order_summary_metrics(self, days: int = 30):
        """Query analítico agrupado: total reservas, ventas y ticket promedio"""
        if self.collection is None:
            return {"period_days": days, "total_orders": 0, "total_revenue": 0.0, "avg_order_value": 0.0}

        since_date = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"event_type": "order_created", "timestamp": {"$gte": since_date}}},
            {
                "$group": {
                    "_id": None,
                    "total_orders": {"$sum": 1},
                    "total_revenue": {"$sum": "$data.total_amount"},
                    "avg_order_value": {"$avg": "$data.total_amount"},
                    "total_hours_booked": {"$sum": "$data.hours"}
                }
            }
        ]
        results = list(self.collection.aggregate(pipeline))
        if results:
            r = results[0]
            return {
                "period_days": days,
                "total_orders": r.get("total_orders", 0),
                "total_revenue": round(float(r.get("total_revenue", 0.0)), 2),
                "avg_order_value": round(float(r.get("avg_order_value", 0.0)), 2),
                "total_hours_booked": r.get("total_hours_booked", 0)
            }
        return {"period_days": days, "total_orders": 0, "total_revenue": 0.0, "avg_order_value": 0.0, "total_hours_booked": 0}

    def get_popular_spaces(self, limit: int = 5):
        """Query analítico: Espacios más demandados"""
        if self.collection is None:
            return []
        pipeline = [
            {"$match": {"event_type": "order_created", "space_id": {"$ne": None}}},
            {
                "$group": {
                    "_id": {"space_id": "$space_id", "space_name": "$data.space_name"},
                    "bookings_count": {"$sum": 1},
                    "total_revenue": {"$sum": "$data.total_amount"}
                }
            },
            {"$sort": {"bookings_count": -1}},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "space_id": "$_id.space_id",
                    "space_name": "$_id.space_name",
                    "bookings_count": 1,
                    "total_revenue": {"$round": ["$total_revenue", 2]}
                }
            }
        ]
        return list(self.collection.aggregate(pipeline))

    def get_active_users(self, hours: int = 24):
        """Query analítico: Usuarios activos en las últimas N horas"""
        if self.collection is None:
            return []
        since = datetime.utcnow() - timedelta(hours=hours)
        pipeline = [
            {"$match": {"timestamp": {"$gte": since}, "user_id": {"$ne": None}}},
            {
                "$group": {
                    "_id": "$user_id",
                    "activity_count": {"$sum": 1},
                    "last_seen": {"$max": "$timestamp"}
                }
            },
            {"$sort": {"activity_count": -1}},
            {
                "$project": {
                    "_id": 0,
                    "user_id": "$_id",
                    "activity_count": 1,
                    "last_seen": {"$dateToString": {"format": "%Y-%m-%dT%H:%M:%SZ", "date": "$last_seen"}}
                }
            }
        ]
        return list(self.collection.aggregate(pipeline))

    def get_recent_events(self, limit: int = 20):
        """Query analítico: Historial de eventos recientes"""
        if self.collection is None:
            return []
        cursor = self.collection.find({}).sort("timestamp", -1).limit(limit)
        events = list(cursor)
        for e in events:
            if "_id" in e:
                e["_id"] = str(e["_id"])
            if isinstance(e.get("timestamp"), datetime):
                e["timestamp"] = e["timestamp"].isoformat()
        return events

# Alias para compatibilidad con main.py
MongoDBAnalyticsClient = MongoDBClient
