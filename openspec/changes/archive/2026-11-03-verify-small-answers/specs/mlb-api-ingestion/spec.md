## ADDED Requirements

### Requirement: Small Low-Volume Answers Are Verified
A single, non-paginated MLB request that belongs to a call of at most `verify_max_requests` requests (default 5; 0 disables) and whose first answer is a 200 of at most `verify_max_bytes` bytes (default 1,000,000) MUST be fetched a second time. Identical bodies MUST be stored as they are. Differing bodies MUST trigger a third fetch, the largest body MUST be kept (ties: the latest) and a `provider_inconsistent` warning naming the endpoint and the sizes MUST be logged. Calls with more requests, larger answers, paginated pools, the hydrate fallback and non-200 answers MUST NOT be verified.

#### Scenario: A partial first answer is replaced by the full one
- **GIVEN** a one-request endpoint whose first answer holds 3 of 5 records and whose next answers hold all 5
- **WHEN** it is ingested
- **THEN** all 5 records are stored, three requests were made and the warning names the sizes.
- Verified by `tests/test_verify_small_answers.py::test_a_partial_first_answer_is_replaced_by_the_full_one`.

#### Scenario: Identical answers cost one extra request
- **WHEN** the two answers are identical
- **THEN** exactly two requests are made and no warning is logged.
- Verified by `tests/test_verify_small_answers.py::test_identical_answers_cost_exactly_one_extra_request`.

#### Scenario: Big, many, disabled and non-200 answers are not verified
- **WHEN** the answer exceeds `verify_max_bytes`, the call has more than `verify_max_requests` requests, `verify_max_requests` is 0, or the status is not 200
- **THEN** one request is made per request of the call.
- Verified by `tests/test_verify_small_answers.py::test_big_many_disabled_and_non_200_answers_are_not_verified`.

#### Scenario: All answers different keeps the largest
- **WHEN** three answers all differ
- **THEN** the largest is stored and the warning is logged.
- Verified by `tests/test_verify_small_answers.py::test_three_different_answers_keep_the_largest_and_warn`.
