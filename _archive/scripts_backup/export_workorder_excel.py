"""
工单小管家 - 导出Excel脚本
访问明细查询页面，导出工单的包装列表
"""
import asyncio
import os
import glob
import time
from playwright.async_api import async_playwright

async def export_workorder_excel():
    """导出工单Excel文件"""
    download_dir = "D:/TechTeam/Data/工单导出"
    os.makedirs(download_dir, exist_ok=True)

    # 记录已有的xlsx文件
    existing_files = set(glob.glob(os.path.join(download_dir, "*.xlsx")))

    async with async_playwright() as p:
        # 窗口最大化配置
        browser = await p.chromium.launch(
            headless=False,
            args=['--start-maximized', '--window-position=1920,0']
        )

        context = await browser.new_context(
            viewport=None,
            no_viewport=True,
            locale='zh-CN',
            accept_downloads=True
        )

        page = await context.new_page()

        try:
            # 1. 访问工单小管家
            print("[1/6] 访问工单小管家...")
            await page.goto("http://172.17.10.165:5003", timeout=30000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # 截图记录初始页面
            await page.screenshot(path=f"{download_dir}/step1_homepage.png")
            print("  - 首页截图已保存")

            # 2. 输入工单号查询
            print("[2/6] 输入工单号 SMT-226011401...")

            # 尝试多种选择器找到输入框
            input_selectors = [
                'input[placeholder*="工单"]',
                'input[placeholder*="订单"]',
                'input[placeholder*="请输入"]',
                'input[type="text"]',
                '.el-input__inner',
                'input.ant-input',
                '#workOrderNo',
                '#orderNo'
            ]

            input_found = False
            for selector in input_selectors:
                try:
                    input_elem = page.locator(selector).first
                    if await input_elem.is_visible(timeout=1000):
                        await input_elem.fill("SMT-226011401")
                        input_found = True
                        print(f"  - 找到输入框: {selector}")
                        break
                except:
                    continue

            if not input_found:
                # 尝试使用文本定位
                print("  - 尝试通过文本定位...")
                all_inputs = page.locator('input')
                count = await all_inputs.count()
                for i in range(count):
                    inp = all_inputs.nth(i)
                    if await inp.is_visible():
                        await inp.fill("SMT-226011401")
                        input_found = True
                        print(f"  - 使用第{i+1}个input")
                        break

            await asyncio.sleep(1)
            await page.screenshot(path=f"{download_dir}/step2_input.png")

            # 3. 点击查询按钮
            print("[3/6] 点击查询按钮...")
            query_selectors = [
                'button:has-text("查询")',
                'button:has-text("搜索")',
                'button:has-text("Search")',
                'button.el-button--primary',
                'button[type="submit"]',
                '.search-btn',
                '.query-btn'
            ]

            for selector in query_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        print(f"  - 点击按钮: {selector}")
                        break
                except:
                    continue

            await asyncio.sleep(3)
            await page.screenshot(path=f"{download_dir}/step3_query_result.png")
            print("  - 查询结果截图已保存")

            # 4. 切换到明细查询页面
            print("[4/6] 切换到明细查询页面...")
            detail_selectors = [
                'text=明细查询',
                'text=明细',
                'text=详情',
                '.tab:has-text("明细")',
                '[role="tab"]:has-text("明细")',
                'a:has-text("明细")'
            ]

            for selector in detail_selectors:
                try:
                    tab = page.locator(selector).first
                    if await tab.is_visible(timeout=1000):
                        await tab.click()
                        print(f"  - 切换标签: {selector}")
                        break
                except:
                    continue

            await asyncio.sleep(2)
            await page.screenshot(path=f"{download_dir}/step4_detail.png")

            # 5. 查找并点击导出按钮
            print("[5/6] 点击导出按钮...")
            export_selectors = [
                'button:has-text("导出全部批次")',
                'button:has-text("导出")',
                'button:has-text("Export")',
                'button:has-text("下载")',
                '.export-btn',
                '[title*="导出"]',
                'a:has-text("导出")'
            ]

            export_clicked = False
            for selector in export_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        # 等待下载
                        async with page.expect_download(timeout=30000) as download_info:
                            await btn.click()
                            print(f"  - 点击导出: {selector}")

                        download = await download_info.value
                        # 保存下载的文件
                        save_path = os.path.join(download_dir, download.suggested_filename or "export.xlsx")
                        await download.save_as(save_path)
                        print(f"  - 文件已保存: {save_path}")
                        export_clicked = True
                        break
                except Exception as e:
                    print(f"  - {selector} 失败: {str(e)[:50]}")
                    continue

            if not export_clicked:
                print("  - 未能触发下载，尝试直接点击...")
                # 尝试点击所有可能的导出按钮
                buttons = page.locator('button')
                count = await buttons.count()
                for i in range(count):
                    btn = buttons.nth(i)
                    text = await btn.text_content() or ""
                    if "导出" in text or "下载" in text:
                        try:
                            async with page.expect_download(timeout=10000) as download_info:
                                await btn.click()
                            download = await download_info.value
                            save_path = os.path.join(download_dir, download.suggested_filename or "export.xlsx")
                            await download.save_as(save_path)
                            print(f"  - 文件已保存: {save_path}")
                            export_clicked = True
                            break
                        except:
                            continue

            await asyncio.sleep(2)
            await page.screenshot(path=f"{download_dir}/step5_export.png")

            # 6. 检查下载的文件
            print("[6/6] 检查下载的文件...")
            await asyncio.sleep(3)  # 等待文件完全写入

            # 查找新增的xlsx文件
            current_files = set(glob.glob(os.path.join(download_dir, "*.xlsx")))
            new_files = current_files - existing_files

            if new_files:
                downloaded_file = list(new_files)[0]
                print(f"  - 新下载文件: {downloaded_file}")
                return downloaded_file
            else:
                # 返回最新的xlsx文件
                all_xlsx = glob.glob(os.path.join(download_dir, "*.xlsx"))
                if all_xlsx:
                    latest = max(all_xlsx, key=os.path.getmtime)
                    print(f"  - 最新文件: {latest}")
                    return latest
                else:
                    print("  - 未找到Excel文件")
                    return None

        except Exception as e:
            print(f"[错误] {str(e)}")
            await page.screenshot(path=f"{download_dir}/error.png")
            raise
        finally:
            await asyncio.sleep(2)
            await browser.close()

if __name__ == "__main__":
    result = asyncio.run(export_workorder_excel())
    print(f"\n导出结果: {result}")
