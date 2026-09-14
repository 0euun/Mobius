# Mobius 평가 리포트

## 데이터·분할 원칙

- 이진 유해성 분류: KOLD·BEEP·K-MHaS의 허가된 공개 데이터에서 학습/검증/시험을 분리했다.
- 멀티라벨 분류: K-MHaS의 다중 혐오 라벨을 사용했다.
- 시간 기반 백테스트: synthetic replay를 시간순으로만 처리하며, 경보 시점 이후 레코드는 앞선 예측에 사용하지 않는다.
- 수치는 공개 데이터와 synthetic replay 기준이며 실제 피해·플랫폼 전체 성능을 주장하지 않는다.

## 모델 결과

| 모델 | 지표 | 결과 |
| --- | --- | ---: |
| 이진 유해성 분류 | Accuracy | 0.7810 |
| 이진 유해성 분류 | Precision | 0.7680 |
| 이진 유해성 분류 | Recall | 0.8193 |
| 이진 유해성 분류 | F1 | 0.7928 |
| 멀티라벨 공격 유형 | Micro F1 | 0.7852 |
| 멀티라벨 공격 유형 | Macro F1 | 0.6860 |

Macro F1이 Micro F1보다 낮으므로 희소 공격 유형의 성능 편차가 남아 있다. 발표에서는 탐지 결과를 확정 판정이 아닌 검토 우선순위 신호로 설명한다.

## 조기경보 백테스트

`data/synthetic/backtest_cases.jsonl`의 5분 단위 replay 결과:

| Brier score | Precision | Recall | 리드타임 |
| ---: | ---: | ---: | ---: |
| 0.1641 | 0.6667 | 1.0000 | 5분 |

## 재현 명령

```powershell
python services/ml/backtest.py data/synthetic/backtest_cases.jsonl
```
