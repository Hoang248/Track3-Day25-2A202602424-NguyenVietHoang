# Lab 25B — Report

**Họ tên / nhóm:** Nguyễn Việt Hoàng — MSV 2A202602424

**Commit:** COMMIT_HASH_PLACEHOLDER

**Điểm tự động:** 84.0 / 88 (4 điểm còn lại là dữ liệu SLO ẩn, chỉ giảng viên chấm được).

Các bảng dưới đây chạy với simulator seed 25 và RNG của client seed 1; grader chạy thêm seed 26 và 27.
Cost là đơn vị của simulator, không phải tiền thật; mọi mốc thời gian G1–G6/C1 là giây ảo.

## 1. Kết quả Game Day (naive vs của tôi)

Số liệu lấy từ [naive.json](gameday/naive.json) và [resilient.json](gameday/resilient.json).

| Băng | Client | availability | p95 (s) | amplification | retry_ratio | cost/turn | recovery (s) | PASS? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G1 | naive | 0.7194 | 7.157 | 7.738 | 6.738 | 2.163 | 4.0 | FAIL |
| G1 | resilient | 1.0 | 4.817 | 1.06 | 0.001 | 2.094 | 0.0 | PASS |
| G2 | naive | 0.456 | 15.034 | 9.904 | 8.904 | 4.627 | 155.0 | FAIL |
| G2 | resilient | 1.0 | 11.874 | 1.058 | 0.007 | 2.164 | 0.0 | PASS |
| G3 | naive | 1.0 | 4.768 | 1.164 | 0.164 | 2.328 | 0.0 | FAIL |
| G3 | resilient | 1.0 | 4.569 | 1.083 | 0.049 | 2.177 | 0.0 | PASS |
| G4 | naive | 1.0 | 13.764 | 1.004 | 0.004 | 2.008 | 0.0 | FAIL |
| G4 | resilient | 1.0 | 5.626 | 1.014 | 0.002 | 2.072 | 0.0 | PASS |
| G5 | naive | 0.3699 | 5.359 | 17.03 | 16.03 | 2.124 | — | FAIL |
| G5 | resilient | 0.8179 | 5.482 | 1.003 | 0.002 | 2.504 | — | PASS |
| G6 | naive | 0.517 | 4.836 | 12.344 | 11.344 | 2.009 | 0.0 | FAIL |
| G6 | resilient | 0.9983 | 6.05 | 1.061 | 0.023 | 2.171 | 0.0 | PASS |

G5 không có mốc restore nên không tính recovery. Availability của G5 bị chặn trên bởi lượng request
malformed: client không retry lỗi 400 nên không làm provider tệ thêm, nhưng cũng không thể biến một
request sai thành lượt thành công.

Cả 6 băng G1–G6 và băng C1 đều PASS trên seed 25/26/27 (xem [scoreboard.json](scoreboard.json)).
Ngoài ra tôi tự thử thêm 10 seed khác, các bản băng dời mốc sự cố sớm/muộn 40–45 s và bản tăng
cường độ sự cố; client vẫn PASS hết, nên cấu hình không phụ thuộc vào thời điểm cụ thể của băng public.

## 2. Cấu hình client và lý do

| Tham số | Giá trị | Lý do (số liệu seed 25) |
| --- | --- | --- |
| attempt_timeout_s | 8 | G6 availability 0.9983; tăng lên 30 s thì tụt còn 0.9484 (mục 3.2) |
| max_attempts_per_provider | 2 | Chỉ một retry trên cùng provider rồi fail over; G3 retry_ratio 0.049 ≤ 0.10 |
| min_time_left_s | 1 | Không mở attempt khi không còn đủ thời gian trước deadline của lượt |
| backoff_base_s / cap_s | 0.25 / 4 | Full jitter tránh retry đồng loạt; G1 có 0 vi phạm retry-after, amplification 1.06 |
| retry_budget_ratio / min_per_s / max_tokens | 0.1 / 0.5 / 20 | Khi breaker hỏng trên G2, budget kéo retry_ratio từ 0.400 xuống 0.058 (mục 3.1) |
| quota_cooldown_s | 300 | Hết quota thì không retry mà chuyển deployment; G5 client_error_retries = 0, availability 0.8179 |
| breaker.window_size / min_calls | 20 / 10 | Cửa sổ đủ ngắn để bắt kịp sự cố; G2 amplification 1.058, recovery 0 s |
| breaker.failure_rate_threshold | 0.5 | Brown-out 30% ở G3 không làm mở breaker vô ích; availability 1.0, retry_ratio 0.049 |
| breaker.slow_call_s / slow_rate_threshold | 5 / 0.6 | Bắt được call "thành công nhưng chậm" ở G4; p95 5.626 s so với 13.764 s của naive |
| breaker.open_duration_s | 10 | Thử lại primary đủ sớm; primary_share_after_restore = 1.0 ở G2/G4/G6 |
| breaker.half_open_max_probes / half_open_successes | 2 / 2 | Giới hạn probe đang bay khi HALF-OPEN; G2 recovery 0 s |

Bộ tham số này giống giá trị gợi ý của starter. Tôi giữ nguyên sau khi đo vì nó đã đạt mọi check
với biên khá rộng; tôi chưa tối ưu riêng từng tham số. Ba tham số có ảnh hưởng rõ nhất (timeout,
retry budget, lọc theo khả năng tool) được kiểm chứng bằng thí nghiệm ở mục 3.

Cách client xử lý từng loại lỗi:

| Lỗi | Tính vào breaker? | Retry / fallback | Cooldown |
| --- | --- | --- | --- |
| CLIENT_ERROR (400/401/…) | không (chỉ release permit) | GiveUp ngay | không |
| QUOTA_EXHAUSTED | không | chuyển sang deployment kế tiếp | 300 s, không chờ |
| RATE_LIMITED | không | spillover; nếu mọi provider đều bị giới hạn thì chờ ngắn | ≥ retry-after |
| OVERLOADED / SERVER_ERROR / TIMEOUT | có | retry nếu còn lượt, còn budget và kịp deadline; sau đó fallback | do breaker |

Ladder giữ thứ tự alpha → alpha-eu → beta → gamma-mini; call `tool` bỏ gamma-mini vì model này không
hỗ trợ tool calling. Cooldown được chia sẻ theo provider, và lần chờ cooldown để gửi lại vào provider
đã thử vẫn bị trừ retry budget. Kết quả mang permit generation cũ bị bỏ qua; khi attempt bị huỷ hoặc
gặp lỗi không liên quan sức khỏe provider, probe được trả lại.

## 3. Ba thí nghiệm

Số liệu đầy đủ ở [experiments/results.json](experiments/results.json). Mỗi biến thể có file YAML riêng
trong `reports/experiments/`, cùng seed và cùng code; cấu hình chính không bị sửa khi chạy thí nghiệm.

### 3.1 Retry budget là lớp phòng thủ cuối

| Băng | Biến thể | availability | amplification | retry_ratio | recovery (s) |
| --- | --- | --- | --- | --- | --- |
| G2 | control | 1.0 | 1.058 | 0.007 | 0.0 |
| G2 | healthy_breaker_no_budget | 1.0 | 1.058 | 0.007 | 0.0 |
| G2 | broken_breaker_budget | 0.9983 | 1.378 | 0.058 | 0.0 |
| G2 | broken_breaker_no_budget | 0.967 | 1.597 | 0.4 | 32.0 |
| G3 | control | 1.0 | 1.083 | 0.049 | 0.0 |
| G3 | healthy_breaker_no_budget | 1.0 | 1.059 | 0.035 | 0.0 |
| G3 | broken_breaker_budget | 1.0 | 1.136 | 0.068 | 0.0 |
| G3 | broken_breaker_no_budget | 1.0 | 1.162 | 0.158 | 0.0 |

"Broken breaker" nghĩa là đặt `min_calls = 10^9` (breaker không bao giờ mở) và
`max_attempts_per_provider = 5`. "No budget" đặt `ratio = 100`, `max_tokens = 10^9`,
`min_per_s = 10^6`, tức budget không bao giờ cạn.

Khi breaker hoạt động đúng, bật hay tắt budget gần như không khác nhau: trên G2 hai biến thể trùng số,
trên G3 retry_ratio là 0.035 (tắt budget) và 0.049 (bật budget), đều dưới 0.10. Lý do là breaker đã
cắt provider hỏng trước khi retry kịp dồn lên.

Khác biệt chỉ lộ ra khi breaker không làm được việc của nó. Trên G2, giữ budget hạ amplification từ
1.597 xuống 1.378, retry_ratio từ 0.400 xuống 0.058 và recovery từ 32 s về 0 s — biến thể không budget
FAIL check recovery. Trên G3, không budget cho retry_ratio 0.158, vượt ngưỡng 0.10; có budget còn 0.068.

Kết luận: breaker và budget giải quyết hai việc khác nhau. Breaker cô lập một provider đang hỏng; budget
giới hạn tổng lượng retry của cả client, nên vẫn chặn được retry storm trong lúc breaker chưa đủ mẫu
hoặc bị cấu hình sai. Lưu ý là khi đổi chính sách retry/fallback thì thứ tự request tới provider cũng
đổi, nên cùng seed không cho kết quả giống hệt từng call; budget không làm mọi metric tốt hơn trên mọi run.

### 3.2 Timeout 30 giây

| Băng | timeout | availability | p95 lượt thành công (s) | give_up_reasons |
| --- | --- | --- | --- | --- |
| G6 | 8 | 0.9983 | 6.05 | {"no_provider_available": 4} |
| G6 | 30 | 0.9484 | 5.481 | {"deadline": 107, "no_provider_available": 16} |
| G4 | 8 | 1.0 | 5.626 | {} |
| G4 | 30 | 1.0 | 5.608 | {} |

Ở G6, `alpha-eu` treo chứ không trả lỗi. Với timeout 30 s, một attempt rơi vào alpha-eu ăn hết toàn bộ
30 s của user trước khi kịp fail over: availability tụt từ 0.9983 xuống 0.9484 và có 107 lượt bỏ cuộc vì
deadline. p95 nhìn qua có vẻ tốt hơn (6.05 → 5.481 s), nhưng đó là survivorship bias: những lượt bị treo
không thành công nên không nằm trong mẫu latency.

G4 gần như không đổi (availability 1.0 ở cả hai, p95 5.626 / 5.608 s) vì alpha vẫn trả lời (chỉ chậm, không
treo) nên timeout 8 s hay 30 s đều không bị chạm, và slow-call breaker đã chuyển traffic khỏi alpha trong cả hai cấu hình.

Timeout của một attempt nên dựa vào p99 lúc bình thường và phần thời gian còn lại cần cho failover cộng
bước chat, chứ không nên bằng deadline 30 s của cả lượt.

### 3.3 Bỏ lọc tool calling

| Biến thể G6 | availability | incompatible_routes | give_up_reasons |
| --- | --- | --- | --- |
| control | 0.9983 | 0 | {"no_provider_available": 4} |
| bỏ capability filter | 0.8922 | 257 | {"incompatible_model_output": 257} |

Biến thể này chỉ thay hàm `ladder()` trong script thí nghiệm. Khi A sập và beta bị siết rate limit,
257 call `tool` bị đẩy sang gamma-mini — model không có tool calling — và trả về output không dùng được
cho luồng hoàn tiền; availability giảm còn 0.8922.

Giải thích cho PM: gamma-mini rẻ và đang rảnh, HTTP 200 trông như thành công, nhưng khách vẫn không
được hoàn tiền. Khả năng chức năng của model (ở đây là tool calling) phải là điều kiện bắt buộc khi chọn
route, không phải một yếu tố để cân với giá.

## 4. Workflow hoàn tiền

Số liệu từ [workflows.json](workflows.json), 500 session, seed 25.

| Executor | completion | crashes | duplicate refunds | duplicate emails | lost refunds | overpaid (cents) | wasted LLM / crash |
| --- | --- | --- | --- | --- | --- | --- | --- |
| naive | 1.0 | 81 | 128 | 81 | 0 | 1496700 | 1.123 |
| yours | 1.0 | 66 | 0 | 0 | 0 | 0 | 0.303 |

Idempotency key là SHA-256 của cặp `(session_id, step)` mã hoá bằng JSON, nên giống nhau qua mọi
retry/restart của cùng một bước và không bị trùng do ký tự phân cách.

Vì sao cần cả idempotency key lẫn checkpoint:

- **Chỉ có key:** restart sẽ chạy lại classify / lookup / summary từ đầu, tốn thêm LLM call và có thể
  đọc ra state khác lần trước.
- **Chỉ có checkpoint:** nếu payment đã chạy xong mà worker chết trước khi ghi checkpoint, lần chạy lại
  sẽ thanh toán thêm một lần nữa.
- **Ghi checkpoint trước khi chạy step:** step chưa thực hiện bị coi là đã xong → mất hoàn tiền.

Thứ tự đúng là: chạy step với key ổn định → nhận kết quả thành công → ghi checkpoint. `WorkerCrash`
không bị bắt trong executor mà để runner xử lý; `ServiceError` / `ServiceTimeout` được retry có giới hạn.
Exactly-once ở đây là exactly-once *effect*, dựa trên việc payment/email API hỗ trợ idempotency key và
`DurableStore` bền vững.

## 5. Alerting & error budget

Số liệu từ [slo.json](slo.json) và [sli_30d.csv](../data/sli_30d.csv). Tổng theo cửa sổ được tính
bằng prefix sum nên mỗi cửa sổ là O(1). Mỗi rule sinh một episode cho mỗi đoạn firing liên tục
(end tính exclusive). Các rule: page 14.4× (60m & 5m), page 6× (360m & 30m), ticket 1× (4320m & 360m).

| Sự cố | Mong đợi | Naive | Burn-rate | Độ trễ (phút) |
| --- | --- | --- | --- | --- |
| checkout_bug | page | page (1 m) | page (27 m) | 27 |
| provider_outage | page | page (0 m) | page (4 m) | 4 |
| deploy_blip | none | false page | không page | — |
| slow_leak | ticket | bỏ sót | ticket (1337 m) | 1337 |
| degraded_evening | page | page (214 m) | page (291 m) | 291 |
| night_spike | none | false page | không page | — |
| small_bump | none | false page | không page | — |

Burn-rate alerting cho 3 page, 1 ticket và **0 false page**; alert naive cho 7 page, 0 ticket và
3 false page, đồng thời bỏ sót slow_leak. Đổi lại, burn-rate page chậm hơn naive (checkout_bug 27 so
với 1 phút, degraded_evening 291 so với 214 phút) nhưng vẫn trong thời hạn, và không đánh thức on-call
vì những spike tự hết.

Ví dụ small_bump: 20 phút với 12% lỗi chỉ tạo trung bình khoảng 4% lỗi trong cửa sổ 1 giờ (nếu traffic
đều), thấp hơn ngưỡng page nhanh 14.4 × 0.5% = 7.2%, nên điều kiện cửa sổ dài không thoả và không page.

**Error budget 30 ngày:** 25,901,755 request, 55,618 bad, allowed_bad 129,508.8, availability 0.997853.
Đã tiêu **42.95%**, còn **57.05%** budget → `freeze_releases = False`. Theo chính sách budget thì chưa
phải đóng băng release, tuy vậy với tốc độ tiêu hiện tại vẫn nên theo dõi trước các đợt release lớn.

**Vì sao cần cả workflow exactly-once lẫn alerting:** idempotency + checkpoint đảm bảo khi có lỗi thì
không trả tiền trùng hay mất tiền, nhưng không cho ai biết hệ thống đang lỗi nhiều. Alerting cho biết
người dùng đang bị ảnh hưởng và đang tiêu budget nhanh tới đâu, nhưng không ngăn được tác dụng phụ sai.
Một cái bảo vệ tính đúng, cái kia bảo vệ khả năng phát hiện.

## 6. Postmortem — G2 với client naive (blameless)

**Tóm tắt:** từ t=120 đến t=300, alpha mất 75% năng lực GPU. Ba tầng retry của client v1 khuếch đại
tải lên 9.904 attempt cho mỗi logical call, availability chỉ còn 0.456. Provider hồi phục tại t=300
nhưng phải tới t=455 tỷ lệ call thành công mới quay lại ≥ 95% trong cửa sổ 30 s, tức trễ 155 s sau restore.

**Ảnh hưởng:** 1,285 / 2,362 lượt user thất bại, 1,077 lượt thành công. Sự cố hạ tầng kéo dài 180 s,
nhưng thời gian từ trigger tới lúc dịch vụ hồi phục là 335 s. Ngoại suy với traffic trung bình
4 lượt/s trong 30 ngày (10,368,000 lượt) và SLO 99.5% (budget 51,840 lượt lỗi), riêng sự cố này tiêu
khoảng 2.48% error budget của tháng.

![G2: naive và resilient, attempts/s và success ratio](gameday/G2_overload_storm.png)

**Timeline** (mỗi dòng gộp 10 giây từ [CSV của client naive](gameday/naive_G2_overload_storm_timeseries.csv);
success ratio tính trên logical call kết thúc trong khoảng đó, khác với availability tính trên cả lượt user):

| t (s) | Sự kiện | Số liệu |
| --- | --- | --- |
| 100–109 | Trước sự cố | alpha 7.2 attempts/s; 68/68 call thành công (100%) |
| 120–129 | alpha mất 75% năng lực | alpha 6.2 attempts/s; 32/32 call thành công (100%) — hàng đợi bắt đầu dài |
| 150–159 | Retry storm lan rộng | alpha 166.5 attempts/s; 0/49 (0%) |
| 290–299 | Cuối giai đoạn mất GPU | alpha 146.1 attempts/s; 0/41 (0%) |
| 300–309 | Provider hồi phục, client vẫn thất bại | alpha 38.8 attempts/s; 0/18 (0%) |
| 400–409 | 100 s sau restore, backlog và retry vẫn còn | alpha 77.9 attempts/s; 0/40 (0%) |
| 455–464 | Bắt đầu hồi phục theo metric 30 s | alpha 13.0 attempts/s; 90/105 (85.7%) |

**Trigger:** alpha mất 75% GPU, throughput không còn đủ cho traffic bình thường.

**Root cause:** chính sách retry của client v1 — retry ở ba tầng app × gateway × SDK (tối đa 36 attempt
mỗi call), delay cố định không jitter, không phân loại lỗi, không retry budget, không breaker, không
fallback. Việc mất GPU chỉ là trigger; chính cơ chế retry biến một sự cố giảm năng lực thành sập hoàn toàn.

**Vì sao không tự hồi phục sau t=300:** hàng đợi của alpha lúc đó đầy những request mà client đã timeout
và bỏ đi, nhưng server vẫn phải xử lý từng cái. Mỗi lần timeout lại sinh thêm retry, nên tải gửi tới
alpha (38.8–77.9 attempts/s sau restore) vẫn vượt năng lực thực của nó. Hàng đợi dài → timeout/529 →
retry → hàng đợi càng dài: đây là vòng lặp metastable, tự duy trì ngay cả khi nguyên nhân ban đầu đã hết.

**Điều giúp ích:** simulator và CSV cho phép tái hiện chính xác sự cố. Với client mới, breaker cô lập
alpha và fail over sang deployment tương thích: availability G2 đạt 1.0, amplification 1.058, recovery 0 s.

**Điều làm tệ hơn:** retry đồng loạt ở nhiều tầng; timeout phía client không huỷ được công việc đã vào
hàng đợi provider; không có dashboard theo dõi amplification nên không ai thấy tải tăng gấp 10 lần.

Sự cố đến từ thiết kế mặc định của client và việc thiếu kiểm thử tải sau sự cố, không phải lỗi của
người trực hay người deploy.

**Action items:**

| # | Hành động | Loại | Owner | Cách kiểm chứng |
| --- | --- | --- | --- | --- |
| 1 | Chỉ retry ở một tầng, phân loại lỗi, full jitter và retry budget | prevent | Team reliability/client | CI: G2 amplification ≤ 1.6 và G3 retry_ratio ≤ 0.10 trên ≥ 3 seed |
| 2 | Dashboard attempts/call, latency và lỗi theo từng provider; alert burn-rate đa cửa sổ | detect | SRE / on-call | Alert khi amplification > 1.5; replay dữ liệu SLI 30 ngày cho 0 false page |
| 3 | Circuit breaker có slow-call và giới hạn probe HALF-OPEN | mitigate | Team reliability/client | CI: G2 recovery ≤ 30 s, G4 p95 ≤ 10 s, primary share sau restore ≥ 0.8 |
| 4 | Failover có kiểm tra tool calling; rollback nhanh khi tỷ lệ lỗi 400 tăng | prevent / mitigate | Agent platform / release | CI: G6 incompatible_routes = 0, G5 client_error_retries = 0 |

## 7. Một điểm yếu còn lại

Trên G2, p95 của client mới vẫn là 11.874 s: phải có một số call chậm/timeout thì breaker mới đủ mẫu để
mở, và các lượt đó phải fallback. Cost/turn cũng lên 2.164 thay vì khoảng 2 khi primary khỏe, vì phải
dùng beta đắt hơn. Ở G6 vẫn có 4 lượt GiveUp(no_provider_available) khi beta bị siết rate limit và các
provider còn lại đều đang cooldown hoặc đã dùng hết số attempt cho phép.

Hướng cải thiện: thêm admission control dựa trên độ dài hàng đợi, hoặc timeout riêng theo loại task
(call `chat` có thể dùng timeout ngắn hơn `tool`), rồi đo lại availability/cost/recovery trên băng bổ
sung trước khi áp dụng. Ở phía cache, nếu dữ liệu FAQ đổi âm thầm đúng lúc mọi provider sập thì
stale-if-error vẫn có thể trả câu trả lời cũ; và câu hỏi cá nhân vẫn không được trả lời trong outage.

## 8. Cache (Part G)

Số liệu từ [không cache](cache/resilient.json) và [có cache](cache/cached.json), băng C1.

| Client | availability | faq_availability | cache_hit_ratio | stale_served | wrong_answers | outdated_answers | cost/turn | PASS? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| resilient | 0.8373 | 0.8424 | 0.0 | 0 | 0 | 0 | 1.386 | FAIL |
| cached | 0.9124 | 0.9645 | 0.592 | 192 | 0 | 2 | 0.955 | PASS |

| Tham số cache | Giá trị | Lý do |
| --- | --- | --- |
| similarity_threshold | 0.93 | 0.80 gây 181 lỗi other_question; 0.93 cho 0 wrong, hit 0.592; 0.97 chỉ còn hit 0.499 → FAIL |
| ttl_s | 30 | outdated_answers = 2; TTL 60 → 3; TTL 300 → 95 (vượt ngưỡng 15) |
| max_stale_s | 300 | FAQ availability 0.9645; tắt stale (0) còn 0.8529 và stale_served = 0 thay vì 192 |
| max_entries | 500 | Giới hạn bộ nhớ, đủ cho catalog FAQ; LRU đã có test. Chưa thử các giá trị khác |

Cách cache hoạt động: không lookup/store câu hỏi cá nhân; scope gồm `prompt_version`; lookup chọn entry
có cosine cao nhất; tuổi entry tính từ lúc store (hit không gia hạn TTL), entry bị loại khi quá
TTL + max_stale. Webhook xoá mọi entry có `sources` chứa tài liệu đã đổi. Hit còn tươi thì trả ngay
không gọi provider; câu trả lời stale chỉ dùng khi provider đã bỏ cuộc (GiveUp) và được lookup lại ngay
lúc đó, nên một invalidation xảy ra giữa chừng vẫn có hiệu lực.

### 8.1 Ngưỡng similarity

| Ngưỡng | hit ratio | wrong_answers | reason | cost/turn |
| --- | --- | --- | --- | --- |
| 0.8 | 0.61 | 181 | {"other_question": 181} | 1.016 |
| 0.93 | 0.592 | 0 | {} | 0.955 |
| 0.97 | 0.499 | 0 | {} | 1.018 |

Catalog FAQ có nhiều cặp câu hỏi rất gần nhau nhưng khác nghĩa (điều kiện hoàn tiền / thời gian tiền về,
đổi size / đổi màu, ship nội thành / đi tỉnh, phương thức thanh toán / COD). Ở 0.80 cache trả nhầm
181 lần; 0.93 loại hết các lỗi này mà vẫn giữ hit 0.592; 0.97 an toàn nhưng hit tụt dưới 0.50 và
cost/turn lại tăng.

### 8.2 TTL

| TTL (s) | hit ratio | outdated_answers | FAQ availability | cost/turn |
| --- | --- | --- | --- | --- |
| 30 | 0.592 | 2 | 0.9645 | 0.955 |
| 60 | 0.652 | 3 | 0.9645 | 0.915 |
| 300 | 0.731 | 95 | 0.964 | 0.863 |

Thay đổi chính sách hoàn tiền có webhook nên invalidation xử lý được. Bảng phí ship đổi âm thầm, không
có sự kiện nào để invalidate, nên chỉ TTL giới hạn được thời gian trả câu cũ: TTL 300 s cho 95 câu
outdated, vượt xa ngưỡng 15. TTL 60 cũng đạt và rẻ hơn một chút, nhưng tôi chọn 30 để dư biên trên băng
ẩn có thể có nhiều thay đổi âm thầm hơn. Cần lưu ý khi bật stale-if-error, tuổi tối đa của câu trả lời
trong outage là TTL + max_stale, nên TTL không phải đảm bảo freshness tuyệt đối.

### 8.3 Stale-if-error

| max_stale_s | FAQ availability | hit ratio | stale_served | wrong_answers |
| --- | --- | --- | --- | --- |
| 0 | 0.8529 | 0.481 | 0 | 0 |
| 300 | 0.9645 | 0.592 | 192 | 0 |

Không có stale-if-error, FAQ availability giảm 11.16 điểm phần trăm (96.45% → 85.29%). Cửa sổ 300 s
dài hơn khoảng outage 120 s của băng nên các câu FAQ chung vẫn được trả lời trong suốt thời gian mọi
provider sập, mà không phát sinh câu trả lời sai.

**Vì sao không cache câu hỏi cá nhân, kể cả khi key theo user:** trạng thái đơn hàng, tiền hoàn, điểm
thưởng thay đổi liên tục; hai câu hỏi có embedding gần nhau không đảm bảo cùng một giao dịch hay cùng
quyền truy cập. Cache những câu này có nguy cơ lộ dữ liệu của người khác hoặc trả state cũ cho chính
user đó, trong khi lợi ích hit gần như không có.

**Alert khi đang phục vụ stale:** availability người dùng thấy vẫn cao trong lúc mọi provider đã sập,
nên không thể chỉ alert theo availability. Dashboard cần tách availability phía user khỏi tỷ lệ lỗi /
timeout phía provider, trạng thái breaker, tỷ lệ fresh/stale và tuổi entry của cache. Khi tỷ lệ stale
tăng hoặc mọi provider unhealthy thì phải alert cho on-call, dù FAQ vẫn đang được trả lời.
