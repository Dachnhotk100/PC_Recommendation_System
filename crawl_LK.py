import asyncio, json, re, os
import pandas as pd
from playwright.async_api import async_playwright
from tqdm.asyncio import tqdm

# --- CẤU HÌNH ---
INPUT_FILE = "linh_kien_may_tinh_urls.csv"
OUTPUT_FILE = "phongvu_raw_data.csv"
MAX_TABS = 3

async def scrape_one(context, url, sem):
    async with sem:
        page = await context.new_page()
        await page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font", "media"] else r.continue_())
        
        # 1. THÊM CỘT VÀO ĐÂY
        result = {
            "url": url, 
            "product_name": "N/A", 
            "current_price": 0, 
            "product_code": "N/A", # Mã sản phẩm
            "category": "N/A",     # Phân loại
            "specifications": "{}"
        }
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # 2. LẤY TÊN, GIÁ VÀ MÃ SẢN PHẨM (CHỈ LẤY MÃ ĐỊNH DANH - PART NUMBER)
            try:
                result["product_name"] = (await page.locator("h1").inner_text()).strip()
                
                # Lấy giá
                price_txt = await page.locator(".att-product-detail-latest-price").first.inner_text()
                result["current_price"] = int(re.sub(r"\D", "", price_txt))
                
                # 🔴 XỬ LÝ MÃ SẢN PHẨM: Chỉ lấy phần định danh (ví dụ: KDU)
                sku_full = await page.locator(".css-1f5a6jh").first.inner_text()
                # SKU: 240901736 - Ta muốn lấy phần sau dấu gạch ngang hoặc mã cuối
                # Nếu chuỗi là "SKU: 240901736", ta dùng regex bốc mã
                sku_clean = sku_full.replace("SKU:", "").strip()
                
                # Nếu Bình muốn bóc mã từ Tên sản phẩm hoặc SKU theo quy luật nhất định:
                # Giả sử mã sản phẩm là phần cuối cùng của URL hoặc một cụm viết hoa trong tên
                # Ở đây tôi ưu tiên bóc mã định danh từ SKU hoặc cuối URL cho chuẩn
                match = re.search(r'([A-Z0-9]{3,})', sku_clean) 
                result["product_code"] = match.group(1) if match else sku_clean
                
            except: pass

            # 3. LOGIC PHÂN LOẠI TỰ ĐỘNG
            name_lower = result["product_name"].lower()
            if any(k in name_lower for k in ["cpu", "vi xử lý"]): result["category"] = "CPU"
            elif any(k in name_lower for k in ["vga", "card màn hình", "đồ họa"]): result["category"] = "VGA"
            elif "ram" in name_lower: result["category"] = "RAM"
            elif any(k in name_lower for k in ["ssd", "hdd", "ổ cứng"]): result["category"] = "Storage"
            elif any(k in name_lower for k in ["mainboard", "bo mạch chủ"]): result["category"] = "Mainboard"
            elif any(k in name_lower for k in ["nguồn", "psu"]): result["category"] = "PSU"
            elif "case" in name_lower: result["category"] = "Case"

            # 4. XỬ LÝ BẢNG THÔNG SỐ (Giữ nguyên logic Flex của Bình)
            btn = page.get_by_text("Xem thông tin chi tiết", exact=False)
            if await btn.count() > 0:
                await btn.first.click(force=True)
                await page.wait_for_timeout(1000)
            
            await page.wait_for_selector('.css-19vrbri', timeout=5000)
            product_specs = {}
            rows = await page.locator('.css-19vrbri').all()

            for row in rows:
                key_loc = row.locator('div[style*="flex: 2"]')
                value_loc = row.locator('div[style*="flex: 3"]')
                if await key_loc.count() > 0 and await value_loc.count() > 0:
                    k = (await key_loc.first.inner_text()).strip()
                    v = (await value_loc.first.inner_text()).strip()
                    if k: product_specs[k] = v
            
            result["specifications"] = json.dumps(product_specs, ensure_ascii=False)

        except Exception as e:
            print(f"⚠️ Lỗi tại {url}: {e}")
        finally:
            await page.close()
            return result

async def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Thiếu file {INPUT_FILE}")
        return

    df = pd.read_csv(INPUT_FILE)
    urls = df["url"].dropna().unique().tolist() 
    
    print(f"🚀 Chạy Test 5 link - Đã thêm Mã SP & Phân loại...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        sem = asyncio.Semaphore(MAX_TABS)
        
        tasks = [scrape_one(context, url, sem) for url in urls]
        results = []
        
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Đang cào"):
            results.append(await f)
            
        pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
        await browser.close()
        print(f"\n✅ Xong! Bình mở file {OUTPUT_FILE} kiểm tra 2 cột mới nhé.")

if __name__ == "__main__":
    asyncio.run(main())