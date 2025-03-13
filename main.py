from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import numpy as np
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

# สร้าง FastAPI app
app = FastAPI()

# ข้อมูลที่รับเข้ามาจากผู้ใช้
class RatingRequest(BaseModel):
    search_query: str
    case_id: str
    rating_value: int


# ตั้งค่า CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # อนุญาตให้ทุกโดเมนเข้าถึง
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# โหลดโมเดล Sentence-BERT
model = SentenceTransformer("Pornpan/sentenbert_finetuning_for_law")

# ฟังก์ชันเชื่อมต่อฐานข้อมูล
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host="dpg-cv2bao9u0jms738s7sag-a.singapore-postgres.render.com",
            port=5432,
            user="law_database_kjz4_user",
            password="lxwsLau6X6QzsdL4UjPmg4bLPXeRaa2C",
            database="law_database_kjz4"
        )
        return conn
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# ข้อมูลที่รับเข้ามาจากผู้ใช้
class SearchRequest(BaseModel):
    user_input: str

# Endpoint สำหรับค้นหาคดีที่คล้ายกัน
@app.post("/search_cases/")
async def search_cases(request: SearchRequest):
    try:
        # เชื่อมต่อฐานข้อมูล
        conn = get_db_connection()
        cursor = conn.cursor()

        # แปลงข้อความเป็นเวกเตอร์
        query_embedding = model.encode(request.user_input).astype(np.float32).tolist()

        # ค้นหา 10 คดีที่คล้ายที่สุดโดยใช้ Cosine Similarity
        sql = """
        SELECT c.case_id, c.case_text, c.category_id, 1 - (c.case_embedding <=> CAST(%s AS vector(512))) AS similarity
        FROM cases c
        ORDER BY similarity DESC
        LIMIT 10;
        """
        cursor.execute(sql, (query_embedding,))  # ใช้ CAST ให้เป็น vector(512)

        # ดึงผลลัพธ์
        results = cursor.fetchall()

        # ดึงข้อมูลหมวดหมู่จากฐานข้อมูล
        cursor.execute("SELECT category_id, category_name FROM categories")
        categories = cursor.fetchall()
        category_dict = {cat[0]: cat[1] for cat in categories}  # สร้าง dictionary ของ category_id และ category_name

        # จัดรูปแบบข้อมูลส่งกลับ
        case_list = [
            {
                "rank": rank,
                "case_id": case_id,
                "case_text": case_text,  
                "category_id": category_id,  # เพิ่ม category_id ใน response
                "category": category_dict.get(category_id, "ไม่ระบุหมวดหมู่"),
                "similarity": round(similarity, 4),
            }
            for rank, (case_id, case_text, category_id, similarity) in enumerate(results, start=1)
        ]

        # ปิดการเชื่อมต่อ
        cursor.close()
        conn.close()

        return {"message": "ค้นหาสำเร็จ", "cases": case_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")

# Endpoint ใหม่: ดึงข้อมูลคดีเพิ่มเติม
@app.get("/get_case_details/")
async def get_case_details(case_id: str = Query(...)):
    try:
        # เชื่อมต่อฐานข้อมูล
        conn = get_db_connection()
        cursor = conn.cursor()

        # ดึงข้อมูลคดีเพิ่มเติม
        sql = """
        SELECT full_case_text, sections
        FROM cases
        WHERE case_id = %s;
        """
        cursor.execute(sql, (case_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Case not found")

        # ปิดการเชื่อมต่อ
        cursor.close()
        conn.close()

        return {
            "full_case_text": result[0],
            "sections": result[1].split(",") if result[1] else [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")
    
# Endpoint ใหม่: ดึงข้อมูลหมวดหมู่
@app.get("/get_categories/")
async def get_categories():
    try:
        # เชื่อมต่อฐานข้อมูล
        conn = get_db_connection()
        cursor = conn.cursor()

        # ดึงข้อมูลหมวดหมู่
        cursor.execute("SELECT category_id, category_name, icon_url FROM categories")
        categories = cursor.fetchall()

        # ปิดการเชื่อมต่อ
        cursor.close()
        conn.close()

        return [
            {
                "category_id": category[0],
                "category_name": category[1],
                "icon_url": category[2],
            }
            for category in categories
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")
    
# Endpoint สำหรับบันทึกการให้คะแนน
@app.post("/submit_rating/")
async def submit_rating(request: RatingRequest):
    try:
        # เชื่อมต่อฐานข้อมูล
        conn = get_db_connection()
        cursor = conn.cursor()

        # บันทึกการให้คะแนน
        sql = """
        INSERT INTO user_rated (search_query, case_id, rating_value)
        VALUES (%s, %s, %s)
        RETURNING rating_id;
        """
        cursor.execute(sql, (request.search_query, request.case_id, request.rating_value))
        rating_id = cursor.fetchone()[0]

        # Commit การเปลี่ยนแปลง
        conn.commit()

        # ปิดการเชื่อมต่อ
        cursor.close()
        conn.close()

        return {"message": "บันทึกการให้คะแนนสำเร็จ", "rating_id": rating_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")

# Endpoint สำหรับดึงข้อมูลการให้คะแนนทั้งหมด
@app.get("/get_ratings/")
async def get_ratings():
    try:
        # เชื่อมต่อฐานข้อมูล
        conn = get_db_connection()
        cursor = conn.cursor()

        # ดึงข้อมูลการให้คะแนน
        cursor.execute("SELECT rating_id, search_query, case_id, rating_value FROM user_rated")
        ratings = cursor.fetchall()

        # ปิดการเชื่อมต่อ
        cursor.close()
        conn.close()

        return [
            {
                "rating_id": rating[0],
                "search_query": rating[1],
                "case_id": rating[2],
                "rating_value": rating[3],
            }
            for rating in ratings
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")

# Endpoint สำหรับดึงข้อมูลการให้คะแนนของคดีเฉพาะ
from urllib.parse import unquote

@app.get("/get_ratings_by_case/")
async def get_ratings_by_case(case_id: str = Query(...)):
    # โค้ดการทำงาน
    try:
        # ถอดรหัส URL Encoding (ถ้ามี)
        case_id = unquote(case_id)

        # เชื่อมต่อฐานข้อมูล
        conn = get_db_connection()
        cursor = conn.cursor()

        # ดึงข้อมูลการให้คะแนนของคดีเฉพาะ
        cursor.execute(
            "SELECT rating_id, search_query, case_id, rating_value FROM user_rated WHERE case_id = %s",
            (case_id,),
        )
        ratings = cursor.fetchall()

        # ปิดการเชื่อมต่อ
        cursor.close()
        conn.close()

        # ส่งกลับข้อมูลว่างหากไม่พบข้อมูล
        return [
            {
                "rating_id": rating[0],
                "search_query": rating[1],
                "case_id": rating[2],
                "rating_value": rating[3],
            }
            for rating in ratings
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")

@app.get("/get_average_ratings/")
async def get_average_ratings():
    try:
        # เชื่อมต่อฐานข้อมูล
        conn = get_db_connection()
        cursor = conn.cursor()

        # ดึงข้อมูลการให้คะแนนทั้งหมด
        cursor.execute("SELECT case_id, rating_value FROM user_rated")
        ratings = cursor.fetchall()

        # สร้าง dictionary เพื่อเก็บผลรวมและจำนวน rating_value สำหรับแต่ละ case_id
        ratings_map = {}
        for case_id, rating_value in ratings:
            if case_id not in ratings_map:
                ratings_map[case_id] = {
                    "total": 0,
                    "count": 0,
                }
            ratings_map[case_id]["total"] += rating_value
            ratings_map[case_id]["count"] += 1

        # คำนวณค่าเฉลี่ย rating_value สำหรับแต่ละ case_id
        average_ratings = {
            case_id: (data["total"] / data["count"]) if data["count"] > 0 else 0.0
            for case_id, data in ratings_map.items()
        }

        # ปิดการเชื่อมต่อ
        cursor.close()
        conn.close()

        return {"average_ratings": average_ratings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")

# Endpoint สำหรับตรวจสอบสถานะ API
@app.get("/")
async def root():
    return {"message": "Welcome to the Law Case Search API"}

# รัน FastAPI Server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)