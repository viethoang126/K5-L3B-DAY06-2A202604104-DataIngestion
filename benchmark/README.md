# Benchmark: Bộ luật Lao động 2019

File [questions.jsonl](questions.jsonl) có 20 câu, mỗi dòng là một câu dạng JSON. Split và loại câu đã được **chia sẵn trước khi chạy pipeline**. Chỉ cần thay các giá trị `TODO`.

| Split | ID | truc_tiep | dien_dat_lai | dieu_kien_ngoai_le | metadata_filter |
|---|---|---|---|---|---|
| dev | q01–q15 | q01–q05 | q06–q09 | q10–q12 | q13–q15 |
| test | q16–q20 | q16–q17 | q18 | q19 | q20 |

Có tổng cộng 4 câu dùng filter, trong đó 1 câu thuộc test. Đề yêu cầu tối thiểu 3 câu filter và ít nhất 1 câu ở test.

## Các trường

| Trường | Ý nghĩa |
|---|---|
| `id`, `split`, `type` | Đã điền sẵn. Không đổi split sau khi đã chạy thử |
| `question` | Câu hỏi theo cách người dùng thật sẽ hỏi. **Không chép nguyên văn evidence** |
| `expected_answer` | Đáp án ngắn, kèm đủ điều kiện hoặc ngoại lệ nếu có |
| `gold_source_id` | Luôn là `blld-2019` |
| `gold_page` | Danh sách **số trang PDF** (1–93), **không phải số trang in** trên Công báo |
| `dieu` | Số Điều chứa đáp án, ví dụ `46`. Dùng cho phân tích lỗi, không dùng trong query |
| `evidence_quote` | Đoạn **trích nguyên văn** từ PDF, đủ để hỗ trợ đáp án. Nên dài từ một câu trở lên |
| `filter` | `null`, hoặc `{"chuong": "<I–XVII>"}` cho câu metadata. Danh sách chương ở [data/manifest_chapters.csv](../data/manifest_chapters.csv) |
| `alternatives` | Các evidence hợp lệ khác: `[{"gold_page": [n], "evidence_quote": "..."}]` |
| `notes` | Ghi chú, ví dụ nguy cơ rò rỉ hoặc vì sao câu khó |

Ví dụ minh họa định dạng. Đây không phải một câu trong benchmark:

```json
{"id": "q00", "split": "dev", "type": "truc_tiep", "question": "Bộ luật Lao động điều chỉnh những vấn đề gì?", "expected_answer": "Tiêu chuẩn lao động; quyền, nghĩa vụ, trách nhiệm của các bên trong quan hệ lao động; ...", "gold_source_id": "blld-2019", "gold_page": [1], "dieu": 1, "evidence_quote": "Bộ luật Lao động quy định tiêu chuẩn lao động; quyền, nghĩa vụ, trách nhiệm của người lao động", "filter": null, "alternatives": [], "notes": ""}
```

## Cách viết từng loại câu

- **truc_tiep:** hỏi thẳng một quy định, ví dụ thời gian thử việc tối đa hoặc số ngày nghỉ lễ.
- **dien_dat_lai:** cùng loại thông tin nhưng **dùng từ khác văn bản**. Ví dụ hỏi "bị đuổi việc" trong khi văn bản dùng "sa thải" hay "đơn phương chấm dứt". Loại câu này kiểm tra embedding có hiểu nghĩa hay không.
- **dieu_kien_ngoai_le:** đáp án có "trừ trường hợp", "nếu", "không được". `expected_answer` và `evidence_quote` phải chứa **cả phần điều kiện**. Khi chấm grounding, chunk thiếu điều kiện chỉ được 1 điểm.
- **metadata_filter:** chọn khái niệm **xuất hiện ở nhiều chương**, sao cho không có filter thì dễ lấy nhầm chương. Filter đóng vai trò ngữ cảnh do người dùng cung cấp trước, ví dụ "Trong phần quy định về tiền lương, …". Ghi vào `notes`: *"filter là input giả định do người dùng cung cấp"*.
  - Để tìm khái niệm như vậy, chạy `--find` với một cụm từ. Nếu kết quả trải trên nhiều chương thì đó là ứng viên tốt.
  - **Không** chọn filter bằng cách nhìn vào gold page rồi suy ngược lại. Filter phải hợp lý từ góc nhìn của người hỏi.

## Chống rò rỉ giữa dev và test

- Không đặt câu dev và câu test trên **cùng một Điều**.
- Nên lấy các câu test từ những chương không có câu dev, hoặc ít câu dev nhất. Ghi lựa chọn này vào `notes` và vào báo cáo.
- Sau khi đã chạy thử, **không sửa câu test**. Nếu buộc phải sửa, ghi rõ theo [RULES.md](../RULES.md).

## Quy trình

Chạy từ thư mục `starter/`, đã cài `requirements.txt`.

```powershell
# 1. Tìm evidence: in trang PDF, chương và đoạn ngữ cảnh
python scripts/validate_benchmark.py --find "trợ cấp thôi việc"

# 2. Điền questions.jsonl, rồi kiểm tra
python scripts/validate_benchmark.py
```

Script kiểm tra các điểm sau:
- Đủ ≥ 20 câu, ≥ 15 dev, ≥ 5 test, ≥ 3 câu filter và ≥ 1 câu filter ở test. ID không trùng.
- `evidence_quote` thực sự có trên `gold_page`, sau khi chuẩn hóa NFC và gộp khoảng trắng. Cảnh báo nếu evidence còn xuất hiện ở trang khác, để bạn cân nhắc đưa vào `alternatives`.
- Giá trị filter tồn tại trong văn bản, và gold page thuộc đúng chương đó. Nếu không, filter sẽ loại mất đáp án.

Script **không** kiểm tra evidence có đủ để trả lời hay không. Bạn phải tự đọc và xác nhận từng câu.

Evidence vắt qua hai trang sẽ không khớp trên một trang đơn lẻ. Hãy chọn đoạn ngắn hơn nằm gọn trong một trang, hoặc ghi chú vào `notes`.

## Tiêu chí chọn chiến lược (chốt trước khi xem test)

Điền trước khi chạy test và không sửa sau đó.

**Ngày chốt:** 2026-11-16. Lúc chốt chưa có file `results/*_test*`, tức là test chưa được chạy lần nào.

Xét lần lượt từng tiêu chí, chỉ chuyển sang tiêu chí sau khi hai chiến lược bằng nhau ở tiêu chí trước. Mọi số liệu đều lấy trên **dev** (15 câu):

1. **Evidence Hit@3** (n/15). Cao hơn thì thắng. Đây là tiêu chí chính, vì top-3 là ngữ cảnh mà bước sinh câu trả lời thực sự nhận được.
2. **Tuân thủ filter** trên các câu có filter (n/3): số câu có cả top-3 thuộc đúng chương được hỏi. Cao hơn thì thắng. Một chunk sai chương nằm trong top-3 có thể dẫn đến trích nhầm quy định.
3. **Hit@1** (n/15). Cao hơn thì thắng.
4. **Chi phí**: ít chunk hơn, rồi thời gian ingest ngắn hơn thì thắng.

Quy tắc:
- Chênh lệch dưới 1 câu được coi là bằng nhau. Với n/15, chỉ cần khác 1 câu là đã có chênh lệch.
- Kết quả test **chỉ dùng để báo cáo**, không dùng để chọn lại chiến lược hay chỉnh tham số, câu hỏi hoặc code. Nếu test tệ hơn dev, ghi nhận và phân tích trong báo cáo.

**Áp dụng vào kết quả dev** (`starter/results/summary_dev.json`):

| Chiến lược | Hit@3 | Tuân thủ filter | Hit@1 |
|---|---|---|---|
| A | 9/15 | 1/3 | 6/15 |
| B | 14/15 | 1/3 | 12/15 |
| C | 14/15 | 3/3 | 12/15 |

Ở tiêu chí 1, B và C bằng nhau (14/15) và đều hơn A, nên loại A. Ở tiêu chí 2, C đạt 3/3 còn B đạt 1/3. **Chọn C.**
