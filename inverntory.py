from abc import ABC, abstractmethod
import json
import os

DATA_FILE = "items.json"

# =====================================================================
# 1. Observer Pattern: Notification Subsystem (OCP & DIP)
# =====================================================================
class BaseNotifier(ABC):
    """Abstract Observer สำหรับระบบแจ้งเตือน"""
    @abstractmethod
    def send(self, message: str) -> None:
        pass

class ConsoleNotifier(BaseNotifier):
    """Concrete Observer: แจ้งเตือนออกหน้าจอ Console"""
    def send(self, message: str) -> None:
        print(f"\n[ALERT - Console] {message}")

class LogNotifier(BaseNotifier):
    """Concrete Observer: จำลองการบันทึกข้อความแจ้งเตือนลง Log"""
    def send(self, message: str) -> None:
        print(f"\n[AUDIT LOG] Recorded event: {message}")

# =====================================================================
# 2. Factory Pattern: NotifierFactory (OCP)
# =====================================================================
class NotifierFactory:
    """Factory Class สำหรับสร้าง Notifier ตามช่องทางที่ระบุ"""
    @staticmethod
    def create(channel: str) -> BaseNotifier:
        channel_lower = channel.strip().lower()
        if channel_lower == "console":
            return ConsoleNotifier()
        elif channel_lower == "log":
            return LogNotifier()
        else:
            raise ValueError(f"Unknown notification channel: {channel}")

# =====================================================================
# 3. Core Service: InventoryService (Subject ใน Observer Pattern)
# =====================================================================
class InventoryService:
    def __init__(self, observers: list[BaseNotifier] = None):
        # รับ Observers ผ่าน Constructor ตามหลัก Dependency Inversion Principle (DIP)
        self.observers: list[BaseNotifier] = observers if observers is not None else []

    def attach(self, observer: BaseNotifier) -> None:
        """เพิ่ม Observer ในรายการแจ้งเตือน"""
        if observer not in self.observers:
            self.observers.append(observer)

    def detach(self, observer: BaseNotifier) -> None:
        """ลบ Observer ออกจากรายการ"""
        if observer in self.observers:
            self.observers.remove(observer)

    def notify_all(self, message: str) -> None:
        """แจ้งเตือนไปยัง Observer ทุกตัวโดยไม่ขึ้นกับ Channel จริง"""
        for observer in self.observers:
            observer.send(message)

    # -----------------------------------------------------------------
    # Data Access Methods
    # -----------------------------------------------------------------
    def load_data(self) -> dict:
        if not os.path.exists(DATA_FILE):
            return {"products": [], "serials": [], "chat_requests": []}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"products": [], "serials": [], "chat_requests": []}

    def save_data(self, data: dict) -> None:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # -----------------------------------------------------------------
    # US-01, US-04: Filter RAM
    # -----------------------------------------------------------------
    def filter_ram(self, require_rgb: bool = False, sync_system: str = None, 
                   brand: str = None, package_type: str = None, min_capacity: int = None) -> list:
        data = self.load_data()
        results = data.get("products", [])

        if require_rgb:
            results = [p for p in results if p.get("hasRgb") is True]

        if sync_system:
            results = [p for p in results if sync_system in p.get("rgbSyncSystems", [])]

        if brand:
            results = [p for p in results if p.get("brand", "").lower() == brand.lower()]

        if package_type:
            results = [p for p in results if p.get("packageType", "").upper() == package_type.upper()]

        if min_capacity is not None:
            results = [p for p in results if p.get("capacity", 0) >= min_capacity]

        return results

    # -----------------------------------------------------------------
    # US-02: ตัดสต็อกด้วย Serial Number และตรวจสอบการแจ้งเตือนสต็อกต่ำ
    # -----------------------------------------------------------------
    def sell_by_serial(self, serial_number: str) -> tuple[bool, str, str | None]:
        data = self.load_data()
        serials = data.get("serials", [])
        products = data.get("products", [])

        # 1. ตรวจสอบว่ามี Serial Number ในระบบหรือไม่
        target_serial = next((s for s in serials if s.get("serialNumber") == serial_number), None)
        if not target_serial:
            return False, "ไม่พบสินค้า", None

        # 2. ตรวจสอบสถานะการขายซ้ำ (Scenario 4)
        if target_serial.get("status") == "SOLD":
            return False, "Serial Number ดังกล่าวไม่สามารถขายซ้ำได้", None

        # 3. ตรวจสอบสินค้าและจำนวนสต็อก
        target_prod = next((p for p in products if p.get("productId") == target_serial.get("productId")), None)
        if not target_prod or target_prod.get("stockQuantity", 0) <= 0:
            return False, "จำนวนสินค้าคงเหลือไม่พอ", None

        # 4. ตัดสต็อกและเปลี่ยนสถานะ Serial Number
        target_serial["status"] = "SOLD"
        target_prod["stockQuantity"] -= 1

        # 5. ตรวจสอบเงื่อนไขแจ้งเตือนสต็อกต่ำ (BR-03: น้อยกว่า Threshold เท่านั้น)
        alert_msg = None
        threshold = target_prod.get("lowStockThreshold", 0)
        current_stock = target_prod["stockQuantity"]

        if current_stock < threshold:
            alert_msg = f"สินค้า {target_prod['productId']} สต็อกต่ำกว่าเกณฑ์ (คงเหลือ {current_stock} ชิ้น)"
            # ส่งการแจ้งเตือนผ่าน Observers ทั้งหมดตาม Observer Pattern
            self.notify_all(alert_msg)

        # บันทึกข้อมูลลง JSON
        self.save_data(data)
        return True, f"ตัดสต็อกสำเร็จ คงเหลือ {current_stock} ชิ้น", alert_msg

    # -----------------------------------------------------------------
    # US-03: ปรึกษาผู้เชี่ยวชาญผ่านระบบแชท
    # -----------------------------------------------------------------
    def submit_chat_request(self, user_id: str, image_filename: str, staff_online: bool = False) -> tuple[bool, str]:
        valid_extensions = [".png", ".jpg", ".jpeg"]
        if not any(image_filename.lower().endswith(ext) for ext in valid_extensions):
            return False, "รองรับเฉพาะไฟล์รูปภาพ (.png, .jpg, .jpeg) เท่านั้น"

        data = self.load_data()
        if "chat_requests" not in data:
            data["chat_requests"] = []

        status = "ASSIGNED" if staff_online else "WAITING"
        req_id = f"REQ-{len(data['chat_requests']) + 1:03d}"

        new_request = {
            "requestId": req_id,
            "userId": user_id,
            "image": image_filename,
            "status": status
        }
        data["chat_requests"].append(new_request)
        self.save_data(data)

        if staff_online:
            return True, f"สร้างคำขอ {req_id} สำเร็จ ระบบได้แจ้งเตือนพนักงานแล้ว (เป้าหมายตอบกลับภายใน 1 นาที)"
        return True, f"ขณะนี้ไม่มีผู้เชี่ยวชาญออนไลน์ ระบบได้บันทึกคำขอ {req_id} ไว้แล้ว (สถานะ WAITING)"
