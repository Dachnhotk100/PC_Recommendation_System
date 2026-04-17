import asyncio, json, re, os, csv
import pandas as pd
from playwright.async_api import async_playwright
from tqdm.asyncio import tqdm

# --- CẤU HÌNH ---
INPUT_FILE = "laptop_urls.csv" 
OUTPUT_FILE = "laptop_full_data.csv"
MAX_TABS = 5  # Tăng lên 3 để nhanh hơn, nếu máy khỏe Bình có thể để 5

async def scrape_one(context, url, sem, writer, f_handle):
    async with sem:
        page = await context.new_page()
        # Chặn rác để tiết kiệm tài nguyên
        await page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font", "media"] else r.continue_())
        
        result = {
            "url": url, 
            "product_name": "N/A", 
            "current_price": 0, 
            "product_code": "N/A", 
            "category": "Laptop",
            "specifications": "{}"
        }
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # 1. Lấy Tên & Giá
            try:
                result["product_name"] = (await page.locator("h1").inner_text()).strip()
                price_txt = await page.locator(".att-product-detail-latest-price").first.inner_text()
                result["current_price"] = int(re.sub(r"\D", "", price_txt))
            except: pass

            # 2. Lấy Mã hiệu (Model)
            try:
                sku_full = await page.locator(".css-1f5a6jh").first.inner_text()
                sku_clean = sku_full.replace("SKU:", "").strip()
                match = re.search(r'([A-Z0-9\-]{4,})', sku_clean) 
                result["product_code"] = match.group(1) if match else sku_clean
            except: pass

            # 3. Bóc bảng thông số (Logic Flex của Bình + Cuộn trang)
            try:
                # Cuộn trang tìm nút
                btn = page.get_by_text("Xem thông tin chi tiết", exact=False)
                for _ in range(3): 
                    if await btn.count() > 0 and await btn.is_visible(): break
                    await page.mouse.wheel(0, 800); await page.wait_for_timeout(500)

                if await btn.count() > 0:
                    await btn.first.scroll_into_view_if_needed()
                    await btn.first.click(force=True)
                    await page.wait_for_timeout(2000)

                await page.wait_for_selector('.css-19vrbri', timeout=8000)
                
                product_specs = {}
                rows = await page.locator('.css-19vrbri').all()
                for row in rows:
                    key_loc = row.locator('div[style*="flex: 2"]')
                    val_loc = row.locator('div[style*="flex: 3"]')
                    if await key_loc.count() > 0 and await val_loc.count() > 0:
                        k = (await key_loc.first.inner_text()).strip()
                        v = (await val_loc.first.inner_text()).strip()
                        if k: product_specs[k] = v
                
                result["specifications"] = json.dumps(product_specs, ensure_ascii=False)
            except: pass

            # 🔴 GHI DỮ LIỆU NGAY LẬP TỨC
            writer.writerow(result)
            f_handle.flush() # Đẩy dữ liệu xuống ổ cứng ngay

        except Exception as e:
            # Ghi cả dòng lỗi (với spec rỗng) để lần sau không cào lại link lỗi này nữa
            writer.writerow(result)
            f_handle.flush()
        finally:
            await page.close()

async def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Không thấy file {INPUT_FILE}!"); return

    df = pd.read_csv(INPUT_FILE)
    df = df[df['url'].str.contains('phongvu.vn', na=False)]
    all_urls = df["url"].dropna().unique().tolist()

    # --- LOGIC RESUME (CHẠY TIẾP) ---
    done_urls = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            # Đọc các URL đã cào xong từ file output
            df_done = pd.read_csv(OUTPUT_FILE, usecols=["url"])
            done_urls = set(df_done["url"].tolist())
        except: pass
    
    pending_urls = [u for u in all_urls if u not in done_urls]
    print(f"✅ Đã có: {len(done_urls)} | ⏳ Còn lại: {len(pending_urls)}")

    if not pending_urls:
        print("🎉 Đã cào xong toàn bộ link!"); return

    # Mở file ở chế độ Append ('a') để viết tiếp
    file_exists = os.path.isfile(OUTPUT_FILE)
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        fieldnames = ["url", "product_name", "current_price", "product_code", "category", "specifications"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists or os.stat(OUTPUT_FILE).st_size == 0:
            writer.writeheader()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            sem = asyncio.Semaphore(MAX_TABS)
            
            # Tạo danh sách task cho các link còn lại
            tasks = [scrape_one(context, url, sem, writer, f) for url in pending_urls]
            
            # Chạy và hiển thị tiến độ
            for f_task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Laptop"):
                await f_task
                
            await browser.close()
            print(f"\n🚀 HOÀN TẤT CÀO LAPTOP!")

if __name__ == "__main__":
    asyncio.run(main())