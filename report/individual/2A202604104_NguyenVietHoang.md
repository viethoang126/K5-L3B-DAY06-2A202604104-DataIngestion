# Báo cáo cá nhân — Day 6

**Học viên:** Nguyễn Việt Hoàng, MSSV 2A202604104, lớp L3B
**Chủ đề:** Truy xuất điều khoản trong Bộ luật Lao động 2019 (văn bản pháp luật tiếng Việt)

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - **Văn bản:** Bộ luật Lao động số 45/2019/QH14, bản gốc đăng Công báo số 993 + 994 ngày 26/12/2019. Tải từ congbaocdn.chinhphu.vn ngày 2026-11-15. SHA-256 `3c865f3d…b5b6c` được kiểm tra mỗi lần chạy.
  - **Quyền sử dụng:** văn bản quy phạm pháp luật không thuộc đối tượng bảo hộ quyền tác giả (khoản 2 Điều 15 Luật Sở hữu trí tuệ, đã đối chiếu với bản hợp nhất 155/VBHN-VPQH). Vì vậy được lưu PDF trong repo và đưa qua embedding model.
  - **Số trang:** PDF có 94 trang vật lý. Trang được tính là trang có ít nhất 200 ký tự sau chuẩn hóa, gồm **93 trang (1–93)**, tổng 196.793 ký tự. Loại trang 94 vì trống. `page` là số trang vật lý; số trang in trên Công báo bằng trang vật lý cộng 2.
  - **Corpus:** 17 chương, 220 Điều.
  - Chi tiết trong [data/MANIFEST.md](../../data/MANIFEST.md), [manifest.csv](../../data/manifest.csv), [manifest_pages.csv](../../data/manifest_pages.csv) và [manifest_chapters.csv](../../data/manifest_chapters.csv).
- **Chuẩn hóa, lỗi và giới hạn:**
  - **Trích xuất:** dùng PyMuPDF. Không dùng pypdf vì nó tách sai âm tiết tiếng Việt khoảng 1.495 lần ("thỏa thu ận"), trong khi PyMuPDF chỉ khoảng 2 lần. Cách đếm là heuristic regex.
  - **Chuẩn hóa:** chuẩn Unicode NFC; bỏ soft hyphen và ký tự zero-width; gộp khoảng trắng trong từng dòng nhưng giữ xuống dòng; bỏ 186 dòng tiêu đề trang ("CÔNG BÁO/Số…" và số trang). Sau khi làm sạch còn 189.319 ký tự nội dung.
  - **Giới hạn:**
    - Khối chữ ký số của PDF ("Ký bởi: Cổng Thông tin điện tử Chính phủ…") ở trang 1–2 **chưa được lọc**. Nó lọt vào chunk B `d003:s00`, phát hiện khi audit metadata.
    - Văn bản **chưa hợp nhất** các sửa đổi sau 2019 và đã hết hiệu lực một phần. Benchmark chỉ đúng với bản gốc này.
- **Embedding, vector store, metric, lệnh chạy và chi phí:**
  - **Embedding:** `intfloat/multilingual-e5-small` chạy local qua sentence-transformers 6.3.0 (torch 2.15.0, transformers 5.23.0, CPU). Model có 384 chiều, nhận tối đa 512 token, dùng prefix `query: ` và `passage: `, vector được chuẩn hóa L2. Không có chunk nào vượt 512 token: lớn nhất là 165 token ở A và 355 token ở B.
  - **Vector store:** Chroma 1.5.9, `PersistentClient` lưu ở `starter/chroma_db/`, metric cosine, tìm kiếm xấp xỉ bằng HNSW. Có hai collection, `day06_blld_A` và `day06_blld_B`; C dùng lại collection B.
  - **Môi trường:** Python 3.12.10, Windows 11.
  - **Chi phí:** 0 USD, vì không gọi API nào.
  - **Lệnh chạy** (trong `starter/`):
    - `python scripts/validate_benchmark.py`
    - `python -m src.run` (dev)
    - `python -m src.run --split test` (test)
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - **Bắt buộc:** `document_id` (`blld-2019`), `source` (đường dẫn PDF), `page` và `page_end` (kiểu int, vì chunk B có thể trải hai trang).
  - **Trường lọc `chuong`** (string, I–XVII): lấy từ dòng tiêu đề `Chương …` trong văn bản. Với A, gán theo tiêu đề chương gần nhất phía trên **đầu** chunk và có thêm cờ `crosses_chapter`. Với B, gán theo Điều chứa chunk. Lý do chọn: chương là phạm vi chủ đề mà luật tự định nghĩa (ví dụ Chương X: lao động nữ, Chương XIV: tranh chấp lao động), có 17 giá trị phân biệt được và kiểm chứng được trong nguồn.
  - **Trường phụ:** `dieu` (int), `char_start/char_end`, `crosses_page`, `strategy` và `content_hash` (dùng để nạp lại theo kiểu incremental).
  - **ID chunk ổn định:** `blld-2019:A:p067:c03` (theo trang và thứ tự) và `blld-2019:B:d169:s00` (theo Điều và phần).
  - **Kiểm tra nạp lại:** mỗi lần chạy ingest hai lượt. Lượt thứ hai không phải embed chunk nào và số bản ghi giữ nguyên (464 và 278), nghĩa là không có bản ghi trùng. Chunk cũ không còn trong dữ liệu sẽ bị xóa.

## Cấu hình và benchmark

- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):** Cả ba dùng cùng corpus, model, store, top-k = 3 và benchmark.
  - **A (fixed-size):** cửa sổ 500 ký tự, overlap 50, không vượt ra ngoài một trang. Điểm cắt lùi về khoảng trắng gần nhất trong 20% cuối cửa sổ.
  - **B (theo cấu trúc):** mỗi Điều là một chunk, tối đa 1200 ký tự; tiêu đề Chương/Mục đi cùng Điều đầu tiên của nó. Điều dài hơn được chia tiếp theo ranh giới khoản (sau đó mới đến dòng, rồi khoảng trắng). Các phần nối tiếp có tiền tố `[Chương X – Điều N. tên]`.
  - **C:** dùng đúng index B, thêm `where chuong = …` khi câu hỏi có filter. **B–C chỉ khác nhau ở filter**, còn A–B chỉ khác nhau ở cách chunk.
  - Tham số đầy đủ có trong [artifacts/experiment_log.csv](../../artifacts/experiment_log.csv) và `starter/results/run_config.json`.
- **≥20 câu: phân chia dev/test, câu filter và cách kiểm chứng evidence:**
  - **Bộ câu hỏi:** 20 câu trong [benchmark/questions.jsonl](../../benchmark/questions.jsonl).
  - **Dev (15 câu):** 5 câu hỏi trực tiếp, 4 câu diễn đạt lại, 3 câu về điều kiện/ngoại lệ, 3 câu có filter (q13 Chương VIII, q14 Chương X, q15 Chương XI).
  - **Test (5 câu):** q16 và q17 hỏi trực tiếp, q18 diễn đạt lại, q19 hỏi điều kiện, q20 có filter (Chương XIV).
  - **Chống rò rỉ:** dev/test được chia trước khi chạy thử. Câu test lấy từ các chương mà dev không có câu nào (IV, V, XII, XIV).
  - **Kiểm chứng evidence:** mỗi câu có `gold_page`, `dieu` và một `evidence_quote` trích nguyên văn. `validate_benchmark.py` kiểm tra quote có xuất hiện trên đúng `gold_page` không (sau NFC và gộp khoảng trắng), và trang đó có thuộc chương ghi trong filter không. Kết quả kiểm tra: OK.
  - **Định nghĩa hit:** chunk thuộc đúng tài liệu, khoảng `page..page_end` chứa trang gold, và text chunk chứa **trọn** evidence_quote.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test** (ghi ở cuối [benchmark/README.md](../../benchmark/README.md), ngày 2026-11-16):
  1. Evidence Hit@3 trên dev.
  2. Hòa thì xét tuân thủ filter trên dev.
  3. Rồi đến Hit@1 trên dev.
  4. Cuối cùng là số chunk và thời gian ingest.

  Test chỉ dùng để báo cáo. Theo tiêu chí này, A bị loại ở tiêu chí 1 (9/15). B và C hòa ở tiêu chí 1 (14/15), nên xét tiêu chí 2: C đạt 3/3, B đạt 1/3. **Chọn C.**

  Về thứ tự thời gian: tiêu chí được ghi khi `starter/results/` chưa có file test nào. Test được chạy 1 lần lúc `2026-11-15T18:14 UTC` (01:14 ngày 16/11 giờ Việt Nam) theo `summary_test.json`. Sau đó không sửa câu hỏi, tham số hay code nào.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 6/15 | 9/15 | 464 | ingest 66.98 s; truy xuất 0.494 s cho 15 câu* | 0 USD |
| B | dev | 12/15 | 14/15 | 278 | ingest 64.6 s; truy xuất 0.045 s | 0 USD |
| C | dev | 12/15 | 14/15 | 278 (index B) | dùng chung ingest B; truy xuất 0.054 s | 0 USD |
| A | test | 2/5 | 2/5 | 464 | truy xuất 0.156 s cho 5 câu* | 0 USD |
| B | test | 4/5 | 5/5 | 278 | truy xuất 0.015 s | 0 USD |
| C | test | 4/5 | 5/5 | 278 (index B) | truy xuất 0.016 s | 0 USD |

\* Thời gian truy xuất của A **bao gồm cả bước embed câu hỏi**. Vector câu hỏi được cache, nên B và C chỉ tốn thời gian tìm trong Chroma. Thời gian ingest là một lần chạy cold trên CPU laptop, gồm cả bước embed toàn bộ chunk. Lần nạp lại chỉ mất khoảng 0.1 s vì không có chunk nào cần embed.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0.8 (n=10; 2 vị trí mức 0, 8 vị trí mức 1) | 15/15 (source/page/chuong); 9/15 nếu tính cả `dieu` | dev 1/3; test 1/1 | 0: 1 · 1: 0 · 2: 4 — 1.6 |
| B | 2.0 (n=10; 10 vị trí mức 2) | 15/15 | dev 1/3; test 1/1 | 0: 0 · 1: 0 · 2: 5 — 2.0 |
| C | 2.0 (dùng chung chunk với B) | 15/15 | dev 3/3; test 1/1 | 0: 0 · 1: 0 · 2: 5 — 2.0 |


**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- **Trace top-3:** `starter/results/traces_{A,B,C}_{dev,test}.jsonl`. Mỗi dòng gồm câu hỏi, chunk_id, score, text, metadata, cờ hit và cờ tuân thủ filter. Tổng hợp nằm trong `summary_dev.json` và `summary_test.json`.
- **Thống kê chunk và ingest:** `chunk_stats.json` và `ingest_log.json`.
- **Nhãn thủ công:** `audit_coherence.csv` (20 dòng), `audit_metadata_test.csv` (45 dòng) và `audit_grounding_test.csv` (15 dòng). Mỗi dòng đều có lý do.
- **Cách chọn mẫu coherence:** 10 vị trí được cố định trong code trước khi chạy (`COHERENCE_PAGES` trong `run.py`). Đó là điểm giữa văn bản của các trang 1, 10, 19, …, 82, cách đều nhau 9 trang. Ở mỗi chiến lược, lấy chunk chứa vị trí đó.
- **Metadata:** kiểm tra trên 5 câu test × top-3 × 3 chiến lược. Mỗi chunk được đối chiếu với text gốc của từng trang PDF bằng một script độc lập, không dùng code pipeline. Chunk trải hai trang được kiểm tra phần đầu nằm ở `page` và phần cuối nằm ở `page_end`.
- **Grounding:** chấm top-3 của 5 câu test cho từng chiến lược.

## Phân tích và kết luận

- **So sánh A–B (chỉ thay cách chunk):**
  - **Retrieval:** B tốt hơn rõ ở mọi chỉ số. Hit@3 dev tăng từ 9 lên 14/15, test từ 2 lên 5/5. Hit@1 dev tăng từ 6 lên 12/15. Coherence tăng từ 0.8 lên 2.0, grounding từ 1.6 lên 2.0.
  - **Nguyên nhân chính:** A cắt giữa câu, nên evidence bị tách sang hai chunk liền nhau. Cờ `evidence_split_suspected` bật ở dev q01, q09, q11, q15 và test q16, q17. Chunk A cũng thường mất tiêu đề Điều hoặc câu dẫn của danh sách (coherence pos02 và pos09 chỉ đạt 0).
  - **Chi phí:** gần như ngang nhau (54.925 so với 50.420 token, ingest 67 s so với 65 s). Số chunk của B ít hơn 40%.
  - **Đánh đổi:**
    - Chunk B dài hơn (trung vị 677 ký tự so với 496), nên đưa vào ngữ cảnh nhiều chữ hơn.
    - 68 chunk B trải hai trang, nên phải dùng `page_end`.
    - B phụ thuộc vào regex `Chương`/`Điều`, chỉ áp dụng được cho văn bản có cấu trúc như văn bản luật.
- **So sánh B–C (chỉ thay filter):**
  - Hit@1 và Hit@3 giữ nguyên. Tuân thủ filter dev tăng từ 1/3 lên 3/3.
  - Trên test, B đã tự tuân thủ filter ở q20, nên top-3 của B và C giống hệt nhau ở cả 5 câu. **Test không phân biệt được B và C.**
  - Filter giúp loại các Điều "giống chữ nhưng khác phạm vi". Ở bộ luật này, Chương VIII (kỷ luật) và Chương XIV (tranh chấp) đều có nhiều điều về "thời hiệu".
- **Hai ví dụ sai:**
  1. **q11** (dev, điều kiện/ngoại lệ; Điều 107, trang 45, Chương VII; "làm thêm tối đa bao nhiêu giờ mỗi năm, trường hợp nào được nhiều hơn").
     - **B/C:** xếp `d107:s00` (p44–45) ở hạng 1 và `d107:s01` (p45) ở hạng 2, đều đúng Điều. Nhưng Điều 107 dài hơn 1200 ký tự nên bị chia tại ranh giới **khoản 3**, trong khi evidence trải từ cuối khoản 2 ("không quá 200 giờ… trừ trường hợp quy định tại khoản 3") sang đầu khoản 3 ("…không quá 300 giờ…"). Không chunk nào chứa trọn quote, nên Hit@3 trượt ở cả ba chiến lược.
     - **Bài học:** ghép hai chunk liền nhau thì vẫn đủ đáp án, nên Hit@3 dạng substring chặt hơn nhu cầu thực tế. Đây cũng là chi phí của việc chia nhỏ Điều dài. Cách sửa: overlap một câu giữa các phần, hoặc khi truy xuất được một phần thì trả kèm các phần còn lại của cùng Điều.
  2. **q13** (dev, filter Chương VIII; Điều 123, trang 51; "thời hiệu xử lý đối với hành vi vi phạm").
     - **B (không lọc):** hạng 1 đúng là `d123:s00` (Chương VIII, thời hiệu xử lý kỷ luật). Nhưng hạng 2–3 là `d194:s00` (p81) và `d190:s00` (p79), đều thuộc Chương XIV và nói về thời hiệu giải quyết **tranh chấp lao động**, nên top-3 không tuân thủ filter. Nếu đưa cả ba chunk cho bước sinh câu trả lời, các mốc 06 tháng, 09 tháng, 01 năm của tranh chấp có thể bị trộn với thời hiệu kỷ luật (06 hoặc 12 tháng).
     - **C (lọc `chuong = VIII`):** hạng 2–3 đổi thành Điều 126 và 127, cùng chương kỷ luật.
     - Lỗi tương tự trên test: A/q18 không lấy được Điều 62 (grounding 0), vì top-3 là các mảnh Điều 41, Điều 30 và Điều 145 có nhắc "chi phí đào tạo" hoặc "hợp đồng".
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - **Chọn C** theo tiêu chí chốt trước test. C có chất lượng truy xuất như B, cộng thêm khả năng giới hạn phạm vi.
  - **Điều kiện áp dụng:** filter `chuong` phải là **input được cung cấp trước** (ví dụ người dùng chọn chủ đề "Kỷ luật lao động" trên giao diện), không suy ra từ đáp án. Nếu filter sai, C sẽ loại mất đáp án; khi không có filter, C hoạt động y hệt B.
  - **Phạm vi kết luận:** chỉ đúng với một văn bản luật tiếng Việt có cấu trúc Chương/Điều rõ ràng. Không suy rộng cho tài liệu không có cấu trúc.
- **Hạn chế:**
  - **Dữ liệu:**
    - Chỉ có một tài liệu, ở phiên bản chưa hợp nhất.
    - Chữ ký số PDF chưa được lọc.
    - `dieu` của chunk A chỉ ghi Điều ở đầu chunk: 6/15 chunk test của A chứa thêm Điều khác.
    - 14 chunk A vắt qua hai chương nhưng chỉ mang chương ở đầu chunk.
  - **Benchmark:**
    - Câu hỏi do tác giả viết sau khi đọc văn bản, nên từ ngữ dễ trùng với văn bản gốc. Các câu diễn đạt lại chỉ giảm được phần nào.
    - Test chỉ có 5 câu và 1 câu filter, nên mỗi câu chiếm 20 điểm phần trăm và chênh lệch không có ý nghĩa thống kê.
  - **Nhãn:**
    - Nhãn do AI chấm nháp. Tác giả chỉ duyệt 5 ca khó, không có người chấm độc lập.
    - Người chấm đã biết Hit@3 và biết chiến lược được chọn.
    - B và C đạt điểm tối đa trên mẫu nhỏ, nên chưa phân biệt được ở coherence và grounding.
  - **Đo lường:**
    - Thời gian là một lần chạy trên CPU; truy xuất của A gồm cả bước embed câu hỏi.
    - HNSW là tìm kiếm xấp xỉ.
    - Hit@3 dạng substring phạt cả trường hợp evidence bị tách nhưng vẫn đọc được (A/q16, A/q17: tự động báo trượt, nhãn tay grounding 2).
- **Nếu làm lại hoặc mở rộng:**
  - Lọc khối chữ ký số.
  - Thêm overlap khi chia Điều dài, hoặc truy xuất theo kiểu parent–child (khoản → Điều).
  - Thêm metadata `dieu_first/dieu_last` cho chunk fixed-size.
  - Thử hybrid với BM25 cho các con số và thuật ngữ như "thời hiệu", "200 giờ".
  - Mở rộng test lên ít nhất 15 câu, với nhiều câu filter hơn và câu nhiễu giữa các chương.
  - Mời người thứ hai chấm nhãn.
  - Dùng bản hợp nhất mới nhất.

## Sử dụng AI

- **Công cụ:** Claude Code (Claude Opus 5.5) trong VS Code.
- **AI đã hỗ trợ:**
  - Giải thích đề.
  - Tìm nguồn chính thức và căn cứ pháp lý về quyền.
  - Viết code `starter/src/*` và `validate_benchmark.py`.
  - Soạn 20 câu benchmark.
  - Chấm nháp nhãn coherence, metadata và grounding (đọc toàn văn từng chunk, đối chiếu metadata bằng script với text gốc PDF).
  - Soạn nháp `experiment_log.csv` và báo cáo này.
- **Cách kiểm tra:**
  - Mọi evidence được validator xác nhận nằm trên đúng `gold_page`.
  - Kiểm tra nạp lại hai lượt để chứng minh không có bản ghi trùng.
  - Hash của PDF được đối chiếu với manifest.
  - Số liệu trong báo cáo lấy trực tiếp từ `starter/results/`.
  - Tác giả tự chạy `python -m src.run --split test` một lần, sau khi đã chốt tiêu chí chọn chiến lược.
  - Tác giả đã đọc lại 20 câu đối chiếu với PDF, không sửa câu nào.
  - Duyệt nhãn audit: tác giả xem lại 5 ca khó, giữ nguyên cả 5 nhãn. Đó là grounding A/q16 và A/q17 (evidence bị tách giữa hai chunk), coherence A/pos02 và A/pos09 (mất câu dẫn hoặc chủ ngữ), coherence B/pos04 (tên Điều trong tiền tố bị cắt). 75 nhãn còn lại là các ca rõ ràng, chưa được duyệt từng dòng; cột `labeled_by` ghi đúng trạng thái của từng nhãn.
  - Chạy lại trên môi trường mới: tạo `starter/.venv` (Python 3.12.10), cài `requirements.txt`, chạy `validate_benchmark.py` (OK) và `python -m src.run` (dev), thực hiện qua Claude Code trên máy tác giả ngày 2026-11-16. Hit@1, Hit@3 và tuân thủ filter trên dev trùng khớp hoàn toàn với bảng trên. Lần chạy này dùng lại index Chroma có sẵn: `content_hash` không đổi nên không phải embed lại chunk nào, và số bản ghi vẫn là 464 và 278.
- **Phần tác giả tự quyết định:**
  - Chọn corpus là văn bản pháp luật Việt Nam, sau khi cân nhắc và bỏ sách OpenStax.
  - Chỉ dùng một file (bản gốc Bộ luật Lao động 2019 trên Công báo), thay vì ghép thêm văn bản hợp nhất.
  - Dùng Chroma thay cho PostgreSQL + pgvector qua Docker như starter gợi ý.
  - Chốt tiêu chí chọn chiến lược (Hit@3, rồi tuân thủ filter, rồi Hit@1, rồi chi phí) trước khi chạy test.
  - Quyết định giao cho AI chấm nháp nhãn audit, và chịu trách nhiệm duyệt lại các nhãn đó.
