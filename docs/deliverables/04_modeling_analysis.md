# 🔍 Deliverable 4 — Analysis Design and Modeling Strategy

---

## 1. Problem to be solved

### 1.1 What happens now and why it is a problem

A Bicing user who needs to **pick up** or **return** a bicycle can only check availability **at the present moment** (via the official app or the station's own panel). There is no way to anticipate whether, upon arriving at the station in the next few minutes, bikes or free docks will still be available.

This generates two concrete problems, already described in `01_product_idea.md`:

- **Wasted trips**: the user walks to a station that, by the time they arrive, has run out of bikes or docks, because availability changes within minutes (high turnover at peak hours).
- **Suboptimal planning decisions**: without a short-term estimate, the user cannot decide in advance whether to wait, switch stations, or leave a few minutes earlier/later.

### 1.2 Who will use the result and for what decision or action

- **End user of Bicing**: checks the prediction of mechanical bikes (`nbm`) and electric bikes (`nbe`) available **5 and 10 minutes ahead** at the station of interest, and decides whether it is worth traveling now, waiting, or choosing another nearby station.
- **The project team itself** (at this stage): uses exploratory analysis to validate which variables provide real signal to the model before investing training time, and to detect data quality problems (gaps, outliers, stations with series that are too short) that could bias the prediction.

### 1.3 What concrete result should the project produce to be considered useful

- A numerical prediction of `nbm` and `nbe` at **+5 min** and **+10 min** for a given station, with an error (MAE) clearly lower than that of a naive heuristic (e.g., "assume the value does not change from the last known data point").
- Evidence, through data analysis, that the variables incorporated into the model (lags, hour, day of week, holidays, weather, free docks) are justified by real patterns observed in the data and not added arbitrarily.

---

## 2. Proposed data analysis and expected utility

This project is, in essence, a **multivariate and multi-horizon time series prediction** problem (see `03_data_model.md`, section 5.2: `LSTMbicis` class). Therefore, the analysis focuses on **trend, seasonality, autocorrelation, and relationship with exogenous variables**, not on classification or recommendation-system techniques.

### 2.1 Questions we want to answer with the data

1. How does the availability of mechanical and electric bikes (`nbm`, `nbe`) vary throughout the day and week at a station? Are there repeatable hourly patterns (e.g., outbound peaks in the morning, inbound peaks in the afternoon)?
2. How much information does the immediately previous value (`lag_nbm`, `lag_nbe`) provide about the future value? From what horizon does it stop being a reliable predictor on its own?
3. Is there a relationship between the weather (`temperature_c`, `rain`, `wind_speed_10m`, `cloud_cover`, `relative_humidity_2m`) and station usage (for example, less turnover on rainy days)?
4. Do holidays (`is_holiday`) show a different availability pattern than a comparable working day?
5. Is there a relationship between available bikes (`nbm + nbe`) and free docks (`nd`)? Since `capacity ≈ nbm + nbe + nd`, does `nd` provide additional information to the model or is it redundant?
6. How many temporal gaps exist in each station's series (instants without a report) and what proportion of the rows used for training are actually **imputed** (`is_imputed`) rather than real observations?
7. Is the station's behavior stable over the ~5 years of history, or has it changed (new stations, capacity changes, periods without data)?

### 2.2 Descriptive, temporal, and variable-relationship analyses

| Type of analysis | What is studied | Utility for the project |
|---|---|---|
| **Descriptive** | Distribution of `nbm`, `nbe`, `nd` per station: minimum, maximum, mean, gaps. | Detect stations with series that are too short, with almost zero capacity, or with too many imputed values to be reliable. |
| **Temporal (trend)** | Evolution of average availability over years/months per station. | Verify whether the full history (2021–2025) is representative or whether it is better to shorten the training period. |
| **Temporal (seasonality)** | Average hourly profile (`hour_sin/cos`) and weekly profile (`dow_sin/cos`) of `nbm`/`nbe`. | Confirm that the cyclic encoding of hour and day of week (already implemented in `backend/core/features.py`) captures a real pattern and not noise. |
| **Autocorrelation** | ACF/PACF of `nbm` and `nbe` at different lags (5, 10, 15... minutes). | Justify the use of `lag_nbm`/`lag_nbe` as a feature and help decide whether the `LOOKBACK` of 24 steps (2 hours) is appropriate or excessive/insufficient. |
| **Relationship between variables** | Correlation between weather (`rain`, `temperature_c`, `wind_speed_10m`...) and availability; comparison `is_holiday` vs. working day. | Confirm (or discard) that weather and holiday variables provide real signal before keeping them in the final model. |
| **Structural relationship** | Correlation between `nd` and `(nbm + nbe)`; verification of `capacity ≈ nbm + nbe + nd`. | Decide whether `nd` should be kept as an independent feature (see change already applied in `03_data_model.md`, section 5.2) or whether its contribution is marginal. |
| **Data quality** | % of rows with `is_imputed = True` per station; longest detected gaps. | Quantify how much "imputation noise" the model is seeing, and allows filtering out unreliable stations from the training/evaluation set. |

### 2.3 Hypotheses or patterns we want to verify

- **H1**: Bike availability presents a bimodal hourly pattern on working days (drop in the morning at residential stations, rise in the afternoon) and a flatter pattern on holidays.
- **H2**: The value at `t-1` (`lag_nbm`/`lag_nbe`) is the strongest individual predictor for the +5 min horizon, but loses explanatory power at the +10 min horizon, where cyclic and weather variables gain relative weight.
- **H3**: Rain (`rain > 0`) reduces bike turnover (fewer trips), which translates into lower variability of `nbm`/`nbe` during those hours.
- **H4**: `nd` is not completely redundant with `nbm + nbe` because `capacity` can vary slightly between snapshots (maintenance, bikes out of service not counted in any counter), so it provides additional signal.

### 2.4 Visualizations, indicators, or conclusions for the MVP

- **Time series with prediction band**: real vs. predicted `nbm`/`nbe` at +5 and +10 min for a selectable station, as already printed by `backend/core/model.py` (`entrenar_y_predecir`) to the console — candidate for a chart in the React MVP frontend.
- **Hour × day of week heatmap** of average availability, to visually justify hourly/weekly seasonality.
- **Model error indicator**: MAE/MSE on test versus the MAE of the naive heuristic (persistence of the last value), as a "minimum utility" metric of the model.
- **Data quality indicator per station**: % of `is_imputed`, used as a filter to decide which stations are shown as reliable in the MVP.

### 2.5 How this analysis helps understand the problem and support modeling

- **Trend and seasonality** analyses confirm (or correct) the cyclic temporal variables already incorporated in `backend/core/features.py`, avoiding the inclusion of features without empirical justification.
- **Autocorrelation** analysis validates the choice of `LOOKBACK` (24 steps) and the prediction horizons (5 and 10 min) defined in `backend/core/model.py`, or motivates their adjustment if the data shows a different behavior.
- **Weather and holiday relationship** analysis decides which exogenous variables are worth keeping in the feature vector, avoiding overfitting the model with variables that provide no real contribution.
- **Data quality** analysis (gaps and imputation) is essential before trusting the model's evaluation metrics: a low MAE at a station with many imputed values can be misleading.

### 2.6 Justification of the modeling architecture: LSTM vs. ARIMA and simple RNN

Before implementing the `LSTMbicis` class (`backend/core/model.py`), two alternatives were considered: the classical statistical approach **ARIMA/SARIMA(X)** and a **simple RNN** ("vanilla" recurrent, without gates). Both were discarded for different reasons, directly related to the nature of the problem and the data described in the previous sections:

| Criterion | ARIMA / SARIMAX | Simple RNN | LSTM (chosen) |
|---|---|---|---|
| **Number of input variables** | Fundamentally **univariate**; SARIMAX admits exogenous regressors, but in a **linear** and limited way. | Multivariate (same as LSTM): accepts a feature vector per time step. | **Multivariate** naturally: accepts in a single input vector the lags, 6 cyclic temporal variables, `nd`, 5 weather variables, and `is_holiday` without transforming the problem. |
| **Number of outputs (multi-horizon)** | Requires one model (or one re-estimation) per prediction horizon (+5 min, +10 min), or iterating step by step accumulating error. | Multi-output possible (same as LSTM), via final `Dense` layer. | Predicts **both horizons and both targets (`nbm`, `nbe`) in a single pass**, thanks to the final `Dense(n_outputs)` layer. |
| **Non-linear relationships** | Assumes linear relationships between the series, its lags, and exogenous regressors. The relationship between weather, time of day, and bike availability is markedly **non-linear** (see hypotheses H1–H3). | Captures non-linearities (`tanh` activation), same as LSTM, but with less practical capacity to learn them in long sequences (see next row). | `LSTM`/`Dense` layers with non-linear activations (`tanh`, `relu`) capture complex interactions (e.g., "rain only reduces turnover at peak hours") without having to specify them manually. |
| **Long-term dependencies (gradient)** | Does not apply (not a recurrent network). | Suffers from the **vanishing/exploding gradient** problem when backpropagating through many time steps; with `LOOKBACK = 24` steps (2 hours at 5 min) it tends to "forget" information from the first steps of the window. | The forget/input/output gates maintain a **cell state** explicitly designed to propagate gradient and information over the 24 positions of the window without degrading. |
| **Stationarity** | Requires (or transforms via differencing) stationary series; one must manually decide the differencing order and identify `(p,d,q)(P,D,Q)` per station. | Does not require explicit stationarity (shares this advantage with LSTM). | Does not require explicit stationarity: `MinMaxScaler` and `LOOKBACK` windows are enough for the network to learn the dynamics directly from the data. |
| **Scalability to multiple stations** | Would require **fitting and maintaining a separate ARIMA model per station** (hundreds of stations in Bicing), with their own orders and hyperparameters. | Equally scalable as LSTM in design, but with worse expected practical performance (see long-term dependencies). | The same `LSTMbicis` design is reused for any `station_id` without manual structural hyperparameter tuning; in the future, a single shared model across similar stations is viable. |
| **Frequency and imputation noise** | Sensitive to gaps and imputations (`is_imputed`); differencing amplifies the noise of forward-fill segments. | Can use `is_imputed` as a feature (same as LSTM), but early forgetting of information limits its use throughout the entire window. | The network can use `is_imputed` as just another feature, letting the model itself learn to weight the reliability of the data instead of assuming the whole series is equally reliable. |

**Why the simple RNN is specifically discarded**: the `LSTMbicis` architecture uses a `LOOKBACK = 24` step window (2 hours of history at 5-minute resolution) to predict up to 2 steps ahead. A "vanilla" RNN backpropagates the error through these 24 positions without any gradient control mechanism, so in practice it struggles to learn relationships between the beginning of the window (e.g., availability 2 hours ago) and the current instant, especially when combined with the 6 cyclic variables and 5 weather variables at each step. The LSTM solves this through its gates and cell state, maintaining selective memory throughout the entire window, which fits better with the `LOOKBACK` chosen for this problem.

**Conclusion**: since the problem is multivariate (weather + calendar + lags + `nd`), multi-output (`nbm` and `nbe`), multi-horizon (+5 and +10 min), with expected non-linear relationships and a 24-step input window where retaining information from the entire recent history is important, an **LSTM** fits better than ARIMA/SARIMAX (due to its linearity and lack of native multivariate support) and better than a **simple RNN** (due to its difficulty learning dependencies across the entire `LOOKBACK` window). ARIMA and the simple RNN would still be reasonable as **baselines** (along with the naive heuristic in section 1.3) to quantify how much the LSTM actually improves, but not as the final system architecture.

---

## 3. Model inputs and outputs

### 3.1 Input (`X`)

Each input sample is a sequence of `LOOKBACK = 24` steps (2 hours at 5-minute resolution), where each time step contains the following vector of 14 features (generated by `LSTMbicis.preparar_datos`, `backend/core/model.py`):

| Group | Features | Count |
|---|---|---|
| Cyclic temporal | `hour_sin`, `hour_cos`, `dow_sin`, `dow_cos`, `year_sin`, `year_cos` | 6 |
| Autoregressive (lags) | `lag_nbm`, `lag_nbe` | 2 |
| Station capacity | `nd` (free docks) | 1 |
| Weather | `temperature_c`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m` | 5 |
| Calendar / data quality | `is_holiday`, `is_imputed` | 2 |

Input tensor shape: `(n_samples, 24, 14)`. All features are scaled with `MinMaxScaler`, fitted **exclusively** on the training segment (see section 5).

### 3.2 Output (`y`)

The model predicts, in a single pass, **2 targets × 2 horizons = 4 values** per sample:

| Target | +5 min horizon | +10 min horizon |
|---|---|---|
| `nbm` (mechanical bikes) | ✅ | ✅ |
| `nbe` (electric bikes) | ✅ | ✅ |

Output tensor shape: `(n_samples, 4)`, generated by `LSTMbicis.construir_secuencias` by concatenating the value of `nbm`/`nbe` at `i+h-1` for each horizon `h`. The values are scaled with an independent `MinMaxScaler` (`scaler_y`) and inverse-transformed before display, clipped to `>= 0` because `nbm`/`nbe` cannot be negative (it makes no sense to predict "-2 bikes").

---

## 4. Model selection

- **Single candidate architecture evaluated in depth**: `LSTM(64) → Dropout(0.2) → LSTM(32) → Dropout(0.2) → Dense(32, relu) → Dense(4, linear)` (`LSTMbicis.construir_modelo`), compared to the alternatives discarded by design in section 2.6 (ARIMA/SARIMAX, simple RNN).
- **Training hyperparameter selection**: the effective number of epochs is not fixed by hand; `EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)` decides when to stop training and which weights to keep, using **only the validation segment** (never the test segment).
- **Selection criterion**: among different configurations (e.g., number of LSTM units, dropout, `LOOKBACK`), the one adopted as final would be the one that minimizes `val_loss` (MSE on validation), not the test error. Test is reserved exclusively for reporting the final error of the already selected model.
- **Pending completion in future deliverables**: a systematic search (grid/random search) over `LOOKBACK`, LSTM units, and `dropout`, currently set by default (`LOOKBACK = 24`, `64`/`32` units, `dropout = 0.2`) without formal sweeping.

---

## 5. Validation strategy

### 5.1 Detected and corrected problem

In a previous version of `backend/core/model.py`, the same final temporal block of the series was used **twice**: as `validation_data` for `EarlyStopping` (to decide when to stop training and which weights to restore), and then as the **test** set to report the final error (`model.evaluate`). This is an **information leak in model selection**: having influenced which weights are restored (`restore_best_weights=True`), that block is no longer an "unseen" sample, and the MAE/MSE reported as "test" is no longer an independent estimate of generalization error.

### 5.2 Applied correction

`LSTMbicis` now splits the series into **three disjoint chronological segments** (`train → val → test`, see `backend/core/model.py`, `entrenar_y_predecir` method):

```
[ ---------------- train ---------------- ][ --- val --- ][ --- test --- ]
      (model fit + scaler fit)                (EarlyStopping)  (final metric,
                                                                  never seen)
```

- **`train`**: used to adjust the model weights and to fit `scaler_x`/`scaler_y` (prevents scale leakage to validation/test).
- **`val`** (`val_frac`, 10% by default): used only by `EarlyStopping` to decide when to stop training and which weights to restore. It participates in *model selection*, so it cannot be used to report the final error.
- **`test`** (`test_frac`, 10% by default): chronologically after `val`, not seen in either `fit` or `EarlyStopping`. It is the only block on which the final metric is reported (`model.evaluate(X_test, y_test)`).

The split is respected at the sequence level (not at loose rows): `LOOKBACK` windows that cross the train/val or val/test boundary are assigned to the later segment, so that no training sequence contains information (directly or through the window) from the validation or test segment.

### 5.3 Why a chronological split and not random (k-fold)

Because this is a time series with strong autocorrelation (`lag_nbm`/`lag_nbe`, see hypothesis H2), a random `k-fold` would create obvious "temporal leaks": a validation sample could be surrounded in time by training samples, causing the model to predict well due to temporal proximity rather than real generalization to future data. Therefore, the train/val/test split is done in strict chronological order, replicating the real usage scenario (predicting the future from the past).

---

## 6. Evaluation metrics

- **MSE (`loss`)**: training metric (`model.compile(loss="mse")`), penalizes larger errors more; appropriate because a large prediction error (e.g., predicting 8 bikes when there are 0) is more costly to the user than several small errors.
- **MAE (`metrics=["mae"]`)**: metric reported to the user/documentation because it is directly interpretable in the same domain as `nbm`/`nbe` (e.g., "the model is wrong on average by ±0.4 bikes").
- **Comparison baseline (naive heuristic)**: MAE of assuming the value does not change from the last known data point (`lag_nbm`/`lag_nbe` as direct prediction). The model is only considered useful (section 1.3) if its MAE on **test** is clearly lower than that of this heuristic.
- **Breakdown by horizon and by target**: in addition to the aggregated MAE of the 4 outputs, it is recommended to report MAE separately for `nbm`/`nbe` and for +5 min/+10 min, since it is expected (hypothesis H2) that error grows with the horizon.

---

## 7. Risks and limitations

| Risk | Impact | Current mitigation / proposal |
|---|---|---|
| **Train/val/test information leakage** | Optimistic test metric, poorly founded model decisions. | Corrected in section 5: three disjoint chronological segments, test never used in `fit` or `EarlyStopping`. |
| **Series with many imputed values (`is_imputed`)** | The model may learn patterns from the imputation (forward-fill) instead of the real dynamics of the station. | Quantify the % of `is_imputed` per station (section 2.2) and consider excluding or weighting less stations with too many gaps. |
| **Change in station behavior over the 5 years** | A model trained with all the history may not represent recent behavior well if the station changed (capacity, urban context). | Evaluate whether to shorten the training period or give more weight to recent data. |
| **`LOOKBACK` and horizons fixed a priori (24 steps, +5/+10 min)** | They may not be optimal for all stations (a high-turnover station may need less history; a quiet one, more). | Pending: hyperparameter sweep (section 4) using the same chronological validation scheme. |
| **Small validation/test blocks in stations with little history** | With fixed `val_frac`/`test_frac` at 10%, a station with little history could leave val/test blocks too small to be representative. | `LSTMbicis` applies a minimum (`min_block`) linked to `lookback` and horizon, and raises an explicit error if the series is too short to separate the three segments with guarantees. |
| **One model per station** | Does not share information between similar stations; stations with little individual history generalize worse. | Future line already pointed out in section 2.6: explore a shared model across stations. |

---

## Traceability with previous deliverables

- **Regarding `02_required_data.md`**: it is confirmed that the weather variables already redefined in that deliverable (`temperature_c`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m`) are precisely those evaluated in this analysis for their relationship with availability; no new data sources are added or removed.
- **Regarding `03_data_model.md`**: the inclusion of `nd` (free docks) as an input feature, already documented in section 5.2 of that deliverable, is subjected here to empirical verification (hypothesis H4) rather than assumed without further analysis. If the analysis showed that `nd` is completely redundant, `03_data_model.md` would be updated to reflect its exclusion, with a record of the reason.
- **Correction on `03_data_model.md` (section 5.2)**: that deliverable described a 90/10 chronological train/test split in which the test segment itself was passed as `validation_data` to `EarlyStopping`. This deliverable **corrects** that decision: `backend/core/model.py` now separates **three** independent chronological segments (train/val/test, section 5 of this document), so that test never participates in model selection. `03_data_model.md` should be understood as updated by this deliverable on that specific point.
