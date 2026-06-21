# 03 — AI/ML Methods Catalog for an AI-Powered Digital Twin of India's Climate

**Project:** ISRO BAH 2026 PS5 — "AI-Powered Digital Twin of India's Climate"
**Scope of this doc:** A cross-validated, ensemble-oriented catalog of **40+ distinct AI/ML methods** for (a) short-term rainfall + temperature prediction / nowcasting / forecasting over an Indian pilot region, (b) spatial downscaling / super-resolution, (c) multi-source data fusion, (d) bias correction, and (e) capturing monsoon variability, extremes, and drought.
**Frameworks targeted:** PyTorch / TensorFlow.
**Date:** 2026-06-21.

> Design philosophy (per project mandate): build a **rich method ensemble where models cross-verify each other**. No single model is trusted alone. Classical ML gives fast, interpretable, low-variance baselines; deep spatiotemporal nets capture fields and motion; generative/diffusion models add sharp, calibrated extremes; foundation models inject global physics priors; physics-informed and DA-hybrid methods enforce conservation laws and assimilate observations. Their outputs are fused (Section 13) and adversarially scored (Section 15).

> **Companion docs (referenced, not duplicated here):** data sources catalog (IMDAA, IMD 0.25° gridded rainfall, ERA5/ERA5-Land, INSAT-3D/3DR, GPM-IMERG, AWS/ARG networks) — see the data doc; deep data-assimilation design — see the DA doc. This doc gives the **ML hooks** to DA in Section 16.

---

## How to read the catalog

Each method entry has: **Name | Category | What it does | Best use in THIS project | Data needs | Accuracy/skill notes | TF/PyTorch availability | Key reference/repo | Pros / Cons.**

Categories used: `FOUNDATION` (SOTA pretrained weather/climate models), `STDL` (spatiotemporal deep learning), `GEN` (generative/super-resolution/diffusion), `PHYS` (physics-informed / hybrid), `CLASSICAL` (tabular ML & statistics), `UQ` (uncertainty/ensemble), `SSL` (self-supervised / transfer), `DA-ML` (data-assimilation × ML).

Quick index (45 methods):

| # | Method | Category | Primary project use |
|---|--------|----------|---------------------|
| 1 | GraphCast | FOUNDATION | Medium-range deterministic forecast / boundary forcing |
| 2 | Pangu-Weather | FOUNDATION | Medium-range deterministic; fast inference |
| 3 | FourCastNet / FCN v2 (SFNO) | FOUNDATION | Fast global forecast, ensembles |
| 4 | GenCast | FOUNDATION/GEN | Probabilistic ensemble, extremes |
| 5 | ClimaX | FOUNDATION/SSL | Fine-tune for regional forecast & downscaling |
| 6 | Aurora | FOUNDATION | Fine-tunable atmosphere FM; air quality |
| 7 | NeuralGCM | FOUNDATION/PHYS | Hybrid physics+ML, climate-length runs |
| 8 | Stormer | FOUNDATION/STDL | Scalable transformer, low-compute SOTA |
| 9 | FengWu | FOUNDATION | Long-lead skill (>10 d) |
| 10 | FuXi | FOUNDATION | Cascade 15-day forecast |
| 11 | Prithvi WxC | FOUNDATION/SSL | Fine-tune (downscaling, extremes) — open weights |
| 12 | CorrDiff | GEN/FOUNDATION | km-scale generative downscaling |
| 13 | NowcastNet | GEN/PHYS | Extreme-precip nowcasting (physics+GAN) |
| 14 | DGMR | GEN | Radar precip nowcasting (GAN) |
| 15 | MetNet-3 | STDL/FOUNDATION | 0–24 h precip/temp from sparse obs + fusion |
| 16 | Earth2Studio / Earth2MIP | FOUNDATION (infra) | Run/compare many FMs under one API |
| 17 | ConvLSTM | STDL | Rainfall/temp field nowcasting baseline |
| 18 | TrajGRU | STDL | Motion-aware nowcasting |
| 19 | PredRNN / PredRNN++ | STDL | Long-horizon field prediction |
| 20 | E3D-LSTM | STDL | 3D spatiotemporal + attention |
| 21 | U-Net / U-Net++ | STDL/GEN | Downscaling, bias-correction, seg of extremes |
| 22 | ResNet (deep CNN) | STDL | Direct field-to-field regression baseline |
| 23 | Vision Transformer (ViT) | STDL | Backbone for fields; FM ablations |
| 24 | Swin / SwinUNETR | STDL | Hierarchical backbone for downscaling/seg |
| 25 | Temporal Fusion Transformer | STDL/CLASSICAL | Station-level multi-horizon temp/rain + covariates |
| 26 | Informer/Autoformer/FEDformer | STDL | Long-horizon station time series |
| 27 | PatchTST | STDL | Strong long-horizon univariate/multivariate TS |
| 28 | Graph WaveNet | STDL | Station-network (graph) forecasting |
| 29 | STGCN | STDL | Spatiotemporal graph forecasting |
| 30 | ClimODE (Neural ODE) | PHYS/STDL | Continuous-time, advection-aware, UQ |
| 31 | PINNs / DeepPhysiNet | PHYS | Sparse-station reconstruction, constraints |
| 32 | DeepSD | GEN | Stacked SRCNN downscaling baseline |
| 33 | SRGAN / ESRGAN (PhIRE) | GEN | Adversarial super-resolution downscaling |
| 34 | Diffusion / score-based SR | GEN | Stochastic precip downscaling, ensembles |
| 35 | Normalizing flows | GEN/UQ | Density estimation, probabilistic downscaling |
| 36 | XGBoost | CLASSICAL | Strong tabular baseline; bias correction |
| 37 | LightGBM | CLASSICAL | Fast tabular baseline; large feature sets |
| 38 | CatBoost | CLASSICAL | Categorical-heavy tabular; robust defaults |
| 39 | Random Forest / Gradient Boosting | CLASSICAL | Robust baselines, feature importance |
| 40 | SVR / Gaussian Process / Kriging | CLASSICAL/UQ | Spatial interpolation, small-data UQ |
| 41 | ARIMA/SARIMA/SARIMAX & Prophet | CLASSICAL | Classical TS baselines, seasonality |
| 42 | Quantile Regression / EMOS | UQ/CLASSICAL | Calibrated intervals, ensemble post-proc |
| 43 | Analog Ensemble (AnEn) | CLASSICAL/UQ | Cheap probabilistic post-processing |
| 44 | EOF/PCA & Self-Organizing Maps | CLASSICAL | Dim-reduction, regime/pattern fusion |
| 45 | Deep Ensembles / MC-Dropout / BNN / Conformal | UQ | Uncertainty across the whole stack |

---

## 1. FOUNDATION / SOTA WEATHER & CLIMATE MODELS

### 1. GraphCast (Google DeepMind)
- **Category:** FOUNDATION (graph neural network, autoregressive).
- **What it does:** GNN on a multi-scale icosahedral mesh; autoregressively predicts ~227 atmospheric variables at 0.25° on 6-h steps, 10-day rollouts in <60 s on a TPU/GPU.
- **Best use here:** Provides **global boundary/large-scale forcing** for a regional India model; deterministic medium-range backbone whose outputs feed downscaling (CorrDiff/U-Net) and the ensemble combiner. Can be fine-tuned regionally.
- **Data needs:** Trained on ERA5 (1979–2017). To run: ERA5/IFS-analysis initial conditions (2 time steps). Fine-tuning needs GPU(s) + ERA5/IMDAA.
- **Skill:** Beat ECMWF HRES on ~90% of 2760 variable/lead-time targets; SOTA deterministic at the time of release.
- **TF/PyTorch:** Reference is **JAX** (Haiku); PyTorch ports exist via Earth2Studio / community.
- **Reference/repo:** Science 2023 paper https://www.science.org/doi/10.1126/science.adi2336 · arXiv https://arxiv.org/abs/2212.12794 · code https://github.com/google-deepmind/graphcast
- **Pros:** Top deterministic skill; fast inference; open weights. **Cons:** Blurry at long lead (deterministic double-penalty); 0.25° coarse for India local rainfall; JAX learning curve; heavy to fine-tune.

### 2. Pangu-Weather (Huawei Cloud)
- **Category:** FOUNDATION (3D Earth-Specific Transformer, 3DEST).
- **What it does:** 3D transformer with Earth-specific positional priors; hierarchical temporal aggregation (1/3/6/24-h models) for medium-range global forecasts at 0.25°.
- **Best use here:** Alternative deterministic global driver to cross-check GraphCast; very fast inference (seconds) makes it practical for a near-real-time twin.
- **Data needs:** ERA5 for training; ERA5/IFS analysis for inference.
- **Skill:** First AI model to beat ECMWF operational on all variables/lead times; ~10,000× faster than NWP. Strong on cyclone tracks.
- **TF/PyTorch:** Weights as **ONNX**; runnable via `ai-models` (PyTorch/ONNXRuntime).
- **Reference/repo:** Nature 2023 https://www.nature.com/articles/s41586-023-06185-3 · code https://github.com/198808xc/Pangu-Weather · runner https://github.com/ecmwf-lab/ai-models-panguweather
- **Pros:** Fast, accurate, easy to run via ONNX. **Cons:** Deterministic (no native ensemble); coarse for local precip; weights are inference-only (BY-NC-SA, non-commercial).

### 3. FourCastNet / FourCastNet v2 (NVIDIA) — AFNO / SFNO
- **Category:** FOUNDATION (Fourier neural operator transformer).
- **What it does:** v1 uses Adaptive Fourier Neural Operator (AFNO) ViT; v2 uses **Spherical FNO (SFNO)** for stability on the sphere. 0.25°, 6-h steps, stable >1-year rollouts; forecasts wind, temp, precip, water vapor.
- **Best use here:** Extremely cheap global ensembles (perturbed ICs) to feed the probabilistic combiner; a fast "engine" inside the digital twin; baseline neural operator.
- **Data needs:** ERA5; inference from analysis fields.
- **Skill:** Competitive short/medium-range; outstanding speed; good for large ensembles where per-member skill < ECMWF but ensemble spread is useful.
- **TF/PyTorch:** **PyTorch** (NVIDIA PhysicsNeMo / Modulus).
- **Reference/repo:** arXiv https://arxiv.org/abs/2208.05419 · code https://github.com/NVlabs/FourCastNet · PhysicsNeMo docs https://docs.nvidia.com/physicsnemo/25.11/physicsnemo/examples/weather/fcn_afno/README.html
- **Pros:** Blazing fast; cheap ensembles; native PyTorch; well documented. **Cons:** Per-member skill below GraphCast/IFS; spectral methods can smear sharp local precip.

### 4. GenCast (Google DeepMind)
- **Category:** FOUNDATION + GEN (conditional diffusion ensemble).
- **What it does:** Diffusion model on the sphere generating stochastic 15-day ensembles, 12-h steps, 0.25°, >80 variables, ~8 min for a full ensemble on TPU.
- **Best use here:** The **probabilistic backbone** — calibrated ensembles for rainfall/extreme risk, cyclones, and as a "truth-like" sample generator the combiner can blend with cheaper members.
- **Data needs:** ERA5 (4 decades); analysis ICs for inference.
- **Skill:** Beat ECMWF ENS on **97.4%** of 1320 targets; mean CRPS improvement ~4.8% (atmos) / ~7.9% (surface); better extremes & TC tracks.
- **TF/PyTorch:** JAX reference (same repo as GraphCast); runnable via Earth2Studio.
- **Reference/repo:** Nature 2024 / arXiv https://arxiv.org/abs/2312.15796 · blog https://deepmind.google/blog/gencast-predicts-weather-and-the-risks-of-extreme-conditions-with-sota-accuracy/ · code https://github.com/google-deepmind/graphcast
- **Pros:** SOTA probabilistic skill; great for extremes/risk. **Cons:** Compute-heavy; 0.25° coarse; diffusion sampling cost; JAX.

### 5. ClimaX (Microsoft)
- **Category:** FOUNDATION + SSL (ViT, variable tokenization).
- **What it does:** First general weather/climate FM; ViT with variable tokenization + aggregation; pretrained self-supervised on CMIP6; fine-tunes to forecasting, downscaling, projection, climate-model emulation.
- **Best use here:** **Fine-tune on IMDAA/ERA5 over India** for both regional forecast and downscaling — a single backbone for several PS5 tasks; good when labeled data is limited.
- **Data needs:** CMIP6 for pretraining (provided weights available); regional ERA5/IMDAA for fine-tuning.
- **Skill:** Matches/beats task-specific SOTA on several WeatherBench tasks; flexible across resolutions/variables.
- **TF/PyTorch:** **PyTorch** (PyTorch Lightning).
- **Reference/repo:** arXiv https://arxiv.org/abs/2301.10343 · code https://github.com/microsoft/ClimaX · site https://microsoft.github.io/ClimaX/
- **Pros:** Versatile FM; modest fine-tune cost; PyTorch; strong docs. **Cons:** Not the absolute top forecaster; needs care to adapt resolution; pretraining on CMIP6 (model data, not obs) introduces biases.

### 6. Aurora (Microsoft)
- **Category:** FOUNDATION (1.3B-param 3D Swin Transformer + Perceiver encoders).
- **What it does:** Large foundation model of the atmosphere trained on >1M hours of geophysical data; fine-tuned heads for high-res weather, **air quality** (0.4°), ocean waves, TC tracks.
- **Best use here:** Fine-tunable atmosphere FM for India; the **air-quality** head is a bonus dimension for a "climate digital twin" (PM forecasting); strong transfer to data-sparse settings.
- **Data needs:** Pretrained weights released; fine-tune with regional reanalysis/obs.
- **Skill:** Beat operational air-quality sims on 74% of targets; competitive/superior on high-res weather & waves at far lower cost.
- **TF/PyTorch:** **PyTorch**.
- **Reference/repo:** Nature 2024 / arXiv https://arxiv.org/abs/2405.13063 · code https://github.com/microsoft/aurora · project https://www.microsoft.com/en-us/research/project/aurora-forecasting/
- **Pros:** Broad (weather+air quality+waves); strong transfer; PyTorch + open weights. **Cons:** Large model; fine-tuning needs good GPUs; air-quality head needs MERRA-2/CAMS-like inputs.

### 7. NeuralGCM (Google Research)
- **Category:** FOUNDATION + PHYS (differentiable dynamical core + ML physics).
- **What it does:** Hybrid GCM — differentiable solver for large-scale dynamics + learned parameterizations; deterministic & ensemble weather and **climate-length** runs.
- **Best use here:** The "physics-respecting" member of the ensemble; stable long runs (drought/seasonal context), realistic TC tracks, AMIP-like climate sensitivity — cross-checks pure-ML members for physical plausibility.
- **Data needs:** ERA5; JAX/TPU-friendly.
- **Skill:** Competitive with ML & ECMWF ENS for 1–10 days; first ML-based accurate **ensemble**; good spatial bias at long range.
- **TF/PyTorch:** **JAX**.
- **Reference/repo:** Nature 2024 https://www.nature.com/articles/s41586-024-07744-y · arXiv https://arxiv.org/abs/2311.07222 · code https://github.com/google-research/neuralgcm
- **Pros:** Physically consistent; stable for long horizons; ensemble-capable. **Cons:** JAX; heavier to run than pure emulators; coarser than km-scale needs.

### 8. Stormer (UCLA/CMU)
- **Category:** FOUNDATION + STDL (scalable standard transformer).
- **What it does:** Near-vanilla transformer with weather-specific embedding, **randomized dynamics** forecasting (variable lead intervals), and pressure-weighted loss; combine multiple rollouts for accuracy.
- **Best use here:** A **low-compute SOTA** option — strong beyond 7 days with far less data/compute; good candidate to actually train/fine-tune in a hackathon if global skill is needed.
- **Data needs:** WeatherBench 2 / ERA5; trains with much less data than peers.
- **Skill:** Competitive short/medium-range; **outperforms** many methods beyond 7 days on WeatherBench 2; favorable scaling.
- **TF/PyTorch:** **PyTorch**.
- **Reference/repo:** NeurIPS 2024 / arXiv https://arxiv.org/abs/2312.03876 · OpenReview https://openreview.net/forum?id=aBP01akha9
- **Pros:** Simple, scalable, data/compute-efficient; PyTorch. **Cons:** Repo less productionized; still 0.25°-class; ensemble via rollout averaging only.

### 9. FengWu (Shanghai AI Lab)
- **Category:** FOUNDATION (multi-modal transformer, replay buffer).
- **What it does:** Treats each variable as a modality with dedicated encoders/decoders + multi-task learning; iterative forecasting stabilized by a replay buffer.
- **Best use here:** Long-lead deterministic member (skillful to ~10.75–11.25 days) to extend the twin's horizon; FengWu-4DVar variant links to DA (Section 16).
- **Data needs:** ERA5; inference via `ai-models`.
- **Skill:** First to push skillful global forecast past ~10.75 days; later ~11.25 days.
- **TF/PyTorch:** **PyTorch** runner.
- **Reference/repo:** arXiv https://arxiv.org/abs/2304.02948 · runner https://github.com/OpenEarthLab/ai-models-fengwu
- **Pros:** Long-lead skill; DA-coupled variant exists. **Cons:** Inference-oriented release; coarse for local precip.

### 10. FuXi (Fudan / SAIS)
- **Category:** FOUNDATION (cascade of U-Transformers).
- **What it does:** Cascade ML system — separate sub-models for short/medium/long ranges combined for a 15-day forecast; FuXi-2.0 adds sub-seasonal capability.
- **Best use here:** Extends ensemble horizon to 15 days / sub-seasonal context for monsoon intraseasonal oscillations (active/break spells).
- **Data needs:** ERA5.
- **Skill:** 15-day forecasts comparable to ECMWF ensemble mean on key fields; cascade reduces error accumulation.
- **TF/PyTorch:** **PyTorch**.
- **Reference/repo:** npj Clim. Atmos. Sci. / arXiv https://arxiv.org/abs/2306.12873 · code https://github.com/tpys/FuXi
- **Pros:** Strong 15-day & sub-seasonal; cascade limits drift. **Cons:** Multi-model complexity; coarse resolution; heavier pipeline.

### 11. Prithvi WxC (IBM + NASA, ORNL)
- **Category:** FOUNDATION + SSL (2.3B-param encoder-decoder transformer).
- **What it does:** Foundation model trained on 160 MERRA-2 variables with mixed masked-reconstruction + forecasting objective; **scales to global and regional without tiling**; fine-tuned heads for downscaling (×12), gravity-wave parameterization, extremes, hurricane tracks, renewable-energy forecasting.
- **Best use here:** A leading choice to **fine-tune for the India twin** — downscaling and extreme-event heads align exactly with PS5; fully open weights on Hugging Face; sibling **Prithvi-EO-2.0** handles satellite imagery for fusion.
- **Data needs:** Pretrained on MERRA-2 (open weights). Fine-tune with IMDAA/ERA5/INSAT + IMD obs.
- **Skill:** Competitive on downscaling & forecasting benchmarks; designed for transfer to data-limited regional tasks.
- **TF/PyTorch:** **PyTorch** (+ Hugging Face).
- **Reference/repo:** arXiv https://arxiv.org/abs/2409.13598 · weights https://huggingface.co/ibm-nasa-geospatial/Prithvi-WxC-1.0-2300M · code https://github.com/NASA-IMPACT/Prithvi-WxC · EO sibling https://arxiv.org/abs/2412.02732
- **Pros:** Open weights; regional-native; downscaling/extremes heads; NASA-EO synergy (good ISRO-narrative fit). **Cons:** Large; MERRA-2 grid (~0.5°) needs adaptation to India grids; fine-tuning compute non-trivial.

### 12. CorrDiff (NVIDIA) — Residual Corrective Diffusion
- **Category:** GEN + FOUNDATION (two-stage UNet regression + diffusion).
- **What it does:** Downscales 25-km global state to **2-km** regional fields via a deterministic UNet (mean) + diffusion (residual/stochastic detail); captures extremes, typhoons, intense rainfall and multivariate consistency.
- **Best use here:** **Primary generative downscaling engine** — map ERA5/GraphCast 0.25° to km-scale rainfall/temp over an India pilot box; proven on Taiwan CWA WRF radar data; runs in seconds per sample.
- **Data needs:** Paired coarse (ERA5) + high-res target (km-scale model/radar/IMD). Train on regional high-res; ~4 s/sample inference on one RTX 6000 Ada.
- **Skill:** Strong on weather extremes and multivariate relationships vs deterministic SR; published in Communications Earth & Environment 2025.
- **TF/PyTorch:** **PyTorch** (PhysicsNeMo + Earth2Studio).
- **Reference/repo:** arXiv https://arxiv.org/abs/2309.15214 · Comm. Earth Environ. https://www.nature.com/articles/s43247-025-02042-5 · docs https://docs.nvidia.com/physicsnemo/latest/physicsnemo/examples/weather/corrdiff/README.html · inference https://nvidia.github.io/earth2studio/examples/04_corrdiff_inference.html
- **Pros:** SOTA km-scale downscaling; sharp extremes; well-engineered PyTorch. **Cons:** Needs paired high-res training data (the hard part for India); diffusion sampling cost; box-limited (regional).

### 13. NowcastNet (Tsinghua)
- **Category:** GEN + PHYS (physics-conditional deep generative model).
- **What it does:** Unifies a deterministic **evolution network** (advection/physics) with a stochastic generative network; end-to-end optimized; predicts radar precip fields over 2048×2048 km up to 3 h.
- **Best use here:** **Extreme-precipitation nowcasting** for the pilot region using INSAT/radar; physics conditioning gives plausible motion + sharp convective detail (critical for flood warning).
- **Data needs:** Radar/precip composite sequences (US/China in paper; for India: DWR mosaics or INSAT-3D precip).
- **Skill:** Ranked #1 by 62 meteorologists in 71% of cases vs leading methods on extreme events.
- **TF/PyTorch:** **PyTorch** (official release).
- **Reference/repo:** Nature 2023 https://www.nature.com/articles/s41586-023-06184-4 · code https://github.com/wlhgu/nowcastnet (official release referenced in paper)
- **Pros:** Best-in-class extreme nowcasting; physics + generative sharpness. **Cons:** Needs dense radar; 0–3 h horizon only; training data scarcity over India.

### 14. DGMR — Deep Generative Model of Radar (DeepMind + Met Office)
- **Category:** GEN (conditional GAN).
- **What it does:** From 20 min of radar, generates probabilistic 90-min precip nowcasts as realistic "radar movies" (CNN + GAN with spatial/temporal discriminators).
- **Best use here:** Probabilistic 0–90 min precip nowcasting baseline; complements NowcastNet; many open re-implementations make it hackathon-feasible.
- **Data needs:** Radar precip sequences (UK in paper). Open-Climate-Fix and MeteoFrance ports exist.
- **Skill:** Ranked #1 by 58 meteorologists in 89% of cases vs alternatives.
- **TF/PyTorch:** **PyTorch** (community); TF possible.
- **Reference/repo:** Nature 2021 https://www.nature.com/articles/s41586-021-03854-z · code https://github.com/openclimatefix/skillful_nowcasting · MeteoFrance https://github.com/meteofrance/dgmr
- **Pros:** Probabilistic & sharp; many maintained ports. **Cons:** GAN training instability; mode-dropping; needs radar; short horizon.

### 15. MetNet-3 (Google Research + DeepMind)
- **Category:** STDL + FOUNDATION (dense neural weather model).
- **What it does:** Predicts precip, 2-m temp, wind, dew point up to **24 h** at ~1 km / 2-min from **sparse + dense** observations; a "densification" step implicitly does data assimilation in one network pass.
- **Best use here:** Conceptual template for the **0–24 h fusion forecaster** — ingest sparse AWS/ARG stations + dense satellite/radar to produce dense rainfall+temperature fields; directly matches PS5 fusion + nowcasting goals.
- **Data needs:** Mixed sensors (radar, satellite, station point obs).
- **Skill:** SOTA 0–24 h for precip/temp; powers Google's operational nowcasts.
- **TF/PyTorch:** No official weights; **community PyTorch** re-implementations (e.g., openclimatefix/metnet).
- **Reference/repo:** arXiv https://arxiv.org/abs/2306.06079 · blog https://research.google/blog/metnet-3-a-state-of-the-art-neural-weather-model-available-in-google-products/ · community code https://github.com/openclimatefix/metnet
- **Pros:** Unifies fusion+DA+forecast; ideal architecture analog for PS5. **Cons:** No official weights (must train); data-hungry; engineering-heavy.

### 16. Earth2Studio / Earth2MIP (NVIDIA) — orchestration, not a single model
- **Category:** FOUNDATION (inference/benchmark infrastructure).
- **What it does:** Unified PyTorch API to run, chain, and inter-compare AI weather models (FourCastNet, SFNO, Pangu, GraphCast, CorrDiff, etc.), with data sources (ERA5/ARCO, GFS, HRRR, IFS) and IO utilities.
- **Best use here:** The **plumbing for the digital twin** — fetch ICs, run multiple FMs, attach CorrDiff downscaling, export fields for the ensemble combiner — without re-engineering each model.
- **Data needs:** Connects to ARCO-ERA5, CDS, GFS/HRRR/IFS.
- **Skill:** N/A (framework); inherits model skills.
- **TF/PyTorch:** **PyTorch**.
- **Reference/repo:** code https://github.com/NVIDIA/earth2studio · docs https://nvidia.github.io/earth2studio/ · MIP https://github.com/NVIDIA/earth2mip
- **Pros:** Massive time-saver; composable pipelines; many models behind one API. **Cons:** NVIDIA-GPU-centric; abstraction can hide tuning knobs.

---

## 2. SPATIOTEMPORAL DEEP LEARNING (fields & sequences)

### 17. ConvLSTM (Shi et al., 2015)
- **Category:** STDL (convolutional recurrent).
- **What it does:** LSTM with convolutional input-to-state and state-to-state transitions; captures spatiotemporal correlations of fields. The canonical precip-nowcasting net.
- **Best use here:** **Workhorse baseline** for both rainfall and temperature field nowcasting/forecasting over the pilot grid; cheap, well-understood, strong India precedent (multiple Indian-city studies use ConvLSTM).
- **Data needs:** Gridded sequences (IMD 0.25° rain, ERA5 temp, INSAT). Modest GPU.
- **Skill:** Beats FC-LSTM and optical-flow ROVER; solid 0–6 h nowcasting; competitive low-cost baseline.
- **TF/PyTorch:** **Both** (`tf.keras.layers.ConvLSTM2D`; PyTorch community modules).
- **Reference/repo:** arXiv https://arxiv.org/abs/1506.04214
- **Pros:** Simple, fast, robust; built into Keras; great cross-check baseline. **Cons:** Blurs at longer lead; fixed receptive field; struggles with fast/rotational motion.

### 18. TrajGRU (Shi et al., 2017)
- **Category:** STDL (location-variant recurrent).
- **What it does:** Learns location-variant recurrent connection structure (aggregates state along learned trajectories) — better for rotation/translation than ConvGRU/ConvLSTM.
- **Best use here:** Motion-aware nowcasting of advecting rain bands (monsoon convection); upgrade path from ConvLSTM.
- **Data needs:** Radar/precip sequences (HKO-7 in paper).
- **Skill:** Outperforms ConvLSTM/ConvGRU on the HKO-7 benchmark, especially for moving systems.
- **TF/PyTorch:** **PyTorch** (e.g., Hzzone/Precipitation-Nowcasting); TF possible.
- **Reference/repo:** NeurIPS 2017 / arXiv https://arxiv.org/abs/1706.03458 · code https://github.com/Hzzone/Precipitation-Nowcasting
- **Pros:** Better motion modeling; established benchmark. **Cons:** More complex/slower than ConvLSTM; still blurs extremes.

### 19. PredRNN / PredRNN++ (Wang et al.)
- **Category:** STDL (spatiotemporal memory).
- **What it does:** ST-LSTM with zig-zag memory flow (PredRNN) and Causal LSTM + Gradient Highway (PredRNN++) for deeper-in-time learning; strong video/field prediction.
- **Best use here:** Longer-horizon field rollouts (multi-hour) where ConvLSTM degrades; good for capturing growth/decay of convective systems.
- **Data needs:** Gridded sequences; more compute than ConvLSTM.
- **Skill:** SOTA-class on Moving-MNIST, radar, traffic; PredRNN++ reduces long-term error accumulation.
- **TF/PyTorch:** **PyTorch** (official `thuml/predrnn-pytorch`).
- **Reference/repo:** TPAMI 2023 / arXiv https://arxiv.org/abs/2103.09504 · PredRNN++ https://arxiv.org/abs/1804.06300 · code https://github.com/thuml/predrnn-pytorch
- **Pros:** Strong long-horizon memory; maintained code. **Cons:** Heavier/slower; recurrent training can be unstable; still deterministic blur.

### 20. E3D-LSTM (Wang et al., 2019)
- **Category:** STDL (3D conv + self-attention memory).
- **What it does:** Eidetic 3D-LSTM integrates 3D convolutions with self-attention over a memory store for long-term spatiotemporal recall.
- **Best use here:** When short- and long-term dynamics both matter (e.g., diurnal temperature + multi-hour precip evolution); part of the STDL cross-check set.
- **Data needs:** Gridded spatiotemporal cubes; higher memory.
- **Skill:** Strong on video & radar prediction; attention improves long-term memory.
- **TF/PyTorch:** **TensorFlow** (official) + PyTorch ports.
- **Reference/repo:** ICLR 2019 https://openreview.net/forum?id=B1lKS2AqtX · code https://github.com/google/e3d_lstm
- **Pros:** Long-term memory via attention; 3D context. **Cons:** Compute/memory heavy; older codebase.

### 21. U-Net / U-Net++
- **Category:** STDL + GEN (encoder-decoder CNN with skip connections).
- **What it does:** Image-to-image translation; U-Net++ adds nested dense skip pathways for finer detail.
- **Best use here:** Swiss-army net for **downscaling** (coarse→fine regression), **bias correction** (model→obs map), and **segmentation of extremes** (flood/heat masks). The deterministic mean stage inside CorrDiff is a U-Net.
- **Data needs:** Paired input/target grids; trains fast on modest GPUs.
- **Skill:** Very strong, stable baseline for field regression/downscaling; often within a few % of fancier nets on RMSE.
- **TF/PyTorch:** **Both** (segmentation-models, MONAI, smp).
- **Reference/repo:** U-Net https://arxiv.org/abs/1505.04597 · U-Net++ https://arxiv.org/abs/1807.10165
- **Pros:** Fast, reliable, ubiquitous; great default for downscaling/bias-correction. **Cons:** Deterministic (smooth — underestimates extremes/variance unless paired with a generative head).

### 22. ResNet (deep residual CNN)
- **Category:** STDL.
- **What it does:** Residual blocks enable very deep CNNs for stable field-to-field regression/classification.
- **Best use here:** Simple, strong **direct regression** baseline for temperature fields and for residual learning in bias correction/downscaling; backbone for many of the above.
- **Data needs:** Gridded data; light.
- **Skill:** Reliable baseline; ResNet-style models were strong on original WeatherBench.
- **TF/PyTorch:** **Both** (torchvision, keras.applications).
- **Reference/repo:** https://arxiv.org/abs/1512.03385
- **Pros:** Easy, fast, robust; good control baseline. **Cons:** No explicit temporal modeling; smooth outputs.

### 23. Vision Transformer (ViT)
- **Category:** STDL (patch transformer).
- **What it does:** Splits fields into patches → transformer; global attention captures long-range spatial dependencies. Backbone of ClimaX/FourCastNet-class models.
- **Best use here:** Backbone for regional forecast/downscaling experiments and FM ablations; competitive when data is sufficient.
- **Data needs:** Larger datasets than CNNs to shine; pretraining helps a lot.
- **Skill:** SOTA-class with scale/pretraining; weaker than CNNs on small data.
- **TF/PyTorch:** **Both** (timm, keras-cv).
- **Reference/repo:** https://arxiv.org/abs/2010.11929
- **Pros:** Global context; scales well; basis of FMs. **Cons:** Data-hungry; heavier; weaker small-data inductive bias.

### 24. Swin Transformer / SwinUNETR
- **Category:** STDL (hierarchical shifted-window transformer; U-shaped variant).
- **What it does:** Local windowed attention with shifted windows → linear complexity + multi-scale features; SwinUNETR is a Swin-based encoder-decoder for dense prediction/segmentation. Aurora's backbone is a 3D Swin.
- **Best use here:** High-res **downscaling** and **extreme-region segmentation**; efficient backbone when ViT is too costly.
- **Data needs:** Gridded data; moderate compute.
- **Skill:** Strong dense-prediction performance; efficient at high resolution.
- **TF/PyTorch:** **PyTorch** (timm, MONAI for SwinUNETR).
- **Reference/repo:** Swin https://arxiv.org/abs/2103.14030 · Swin-Unet https://arxiv.org/abs/2105.05537 · SwinUNETR https://arxiv.org/abs/2201.01266
- **Pros:** Efficient multi-scale attention; good for high-res. **Cons:** More complex than U-Net; tuning window sizes.

### 25. Temporal Fusion Transformer (TFT)
- **Category:** STDL + CLASSICAL (attention-based multi-horizon TS).
- **What it does:** Combines LSTM local processing + interpretable multi-head attention; native handling of static metadata, known-future inputs, and observed covariates; outputs quantiles.
- **Best use here:** **Station-level** multi-horizon temperature & rainfall forecasting with covariates (elevation, land-use, calendar, ENSO/IOD indices); built-in quantiles feed UQ; interpretable feature/temporal importance for the report.
- **Data needs:** Tabular per-station time series + covariates.
- **Skill:** Strong multi-horizon performance; quantile outputs well-calibrated; interpretable.
- **TF/PyTorch:** **Both** (PyTorch-Forecasting; Darts; original TF).
- **Reference/repo:** Int. J. Forecasting 2021 / arXiv https://arxiv.org/abs/1912.09363
- **Pros:** Quantiles + interpretability + covariates; great per-station model. **Cons:** Per-series/point modeling (not full fields); heavier to tune than GBMs.

### 26. Informer / Autoformer / FEDformer
- **Category:** STDL (long-horizon transformers).
- **What it does:** **Informer** = ProbSparse attention for long sequences; **Autoformer** = series decomposition + auto-correlation; **FEDformer** = frequency-domain (Fourier/wavelet) attention. All target long-horizon TS.
- **Best use here:** Long-horizon **station/grid-cell** temperature & rainfall (seasonal cycle, trends); FEDformer's frequency view suits monsoon periodicity.
- **Data needs:** Long univariate/multivariate series.
- **Skill:** Strong on long-horizon benchmarks (note: simple linear baselines sometimes rival them — always benchmark).
- **TF/PyTorch:** **PyTorch** (Time-Series-Library `thuml/Time-Series-Library`; Nixtla neuralforecast).
- **Reference/repo:** Informer https://arxiv.org/abs/2012.07436 · Autoformer https://arxiv.org/abs/2106.13008 · FEDformer https://arxiv.org/abs/2201.12740 · library https://github.com/thuml/Time-Series-Library
- **Pros:** Purpose-built for long horizons; decomposition aids seasonality. **Cons:** Can be beaten by simpler models; point/series-level, not fields.

### 27. PatchTST
- **Category:** STDL (patching + channel-independent transformer).
- **What it does:** Splits each series into subseries **patches** as tokens with channel independence; strong, efficient long-horizon TS forecasting + good transfer/self-supervision.
- **Best use here:** A top **station-level** long-horizon baseline for temperature/rainfall; cheap and robust; good cross-check vs TFT and GBMs.
- **Data needs:** Long series; light compute.
- **Skill:** SOTA-class on long-horizon benchmarks; robust and simple.
- **TF/PyTorch:** **PyTorch** (neuralforecast; official).
- **Reference/repo:** ICLR 2023 / arXiv https://arxiv.org/abs/2211.14730 · code https://github.com/yuqinie98/PatchTST
- **Pros:** Strong, efficient, easy; self-supervised pretraining option. **Cons:** Univariate-centric; not spatial.

### 28. Graph WaveNet
- **Category:** STDL (spatiotemporal GNN).
- **What it does:** Adaptive graph convolution + dilated causal TCN; learns the adjacency between nodes automatically.
- **Best use here:** Forecasting over the **irregular network of AWS/ARG stations** (nodes) where Euclidean grids don't fit; learns station inter-dependencies (e.g., upwind→downwind rainfall).
- **Data needs:** Multivariate node time series + (optional) adjacency.
- **Skill:** Strong traffic/sensor-network benchmarks; learned graph beats fixed graphs.
- **TF/PyTorch:** **PyTorch** (PyTorch Geometric Temporal).
- **Reference/repo:** IJCAI 2019 / arXiv https://arxiv.org/abs/1906.00121
- **Pros:** Native for station networks; auto-learns spatial graph. **Cons:** Graph construction/scaling; not for dense fields directly.

### 29. STGCN (Spatio-Temporal GCN)
- **Category:** STDL (spatiotemporal GNN).
- **What it does:** Stacks gated temporal convolutions with graph convolutions in ST-blocks; fully convolutional (fast).
- **Best use here:** Alternative/cross-check to Graph WaveNet for station-network temperature/rainfall; fast to train.
- **Data needs:** Node series + predefined graph (distance/correlation).
- **Skill:** Strong, efficient spatiotemporal forecasting baseline.
- **TF/PyTorch:** **PyTorch** (PyG-Temporal); TF available.
- **Reference/repo:** IJCAI 2018 / arXiv https://arxiv.org/abs/1709.04875
- **Pros:** Fast, simple, effective on graphs. **Cons:** Needs predefined graph; fixed adjacency limits adaptivity.

---

## 3. PHYSICS-INFORMED & HYBRID

### 30. ClimODE (Verma et al., ICLR 2024)
- **Category:** PHYS + STDL (physics-informed Neural ODE).
- **What it does:** Continuous-time advection (mass-conserving transport) as a neural flow, with local conv + global attention; provides built-in uncertainty.
- **Best use here:** Physically grounded, **uncertainty-aware** member that trains on a single GPU — feasible to actually run in the PoC; advection prior suits monsoon transport; cross-checks pure-ML members.
- **Data needs:** ERA5/WeatherBench subset; single-GPU trainable.
- **Skill:** Beats ClimaX, FourCastNet, and a generic Neural ODE across variables with ~10× fewer params.
- **TF/PyTorch:** **PyTorch** (official).
- **Reference/repo:** arXiv https://arxiv.org/abs/2404.10024 · code https://github.com/Aalto-QuML/ClimODE
- **Pros:** Physics prior + UQ; parameter-efficient; single-GPU. **Cons:** ODE solvers add cost; advection assumption imperfect for convective genesis.

### 31. PINNs / DeepPhysiNet / physics-guided NNs
- **Category:** PHYS.
- **What it does:** Embed PDE/conservation residuals into the loss so the network respects physics with sparse data; DeepPhysiNet bridges DL with atmospheric physics for continuous modeling; PINNs reconstruct high-res fields from sparse stations.
- **Best use here:** **High-resolution reconstruction from sparse AWS/ARG stations** (fusion + downscaling where labels are scarce); soft physical constraints for temperature; gap-filling.
- **Data needs:** Sparse obs + governing equations/constraints; careful loss weighting.
- **Skill:** Effective for reconstruction/interpolation under data scarcity; competitive temperature forecasting in recent studies; not yet beating big emulators on full forecasting.
- **TF/PyTorch:** **Both** (DeepXDE, Modulus, NeuralPDE).
- **Reference/repo:** DeepPhysiNet https://arxiv.org/abs/2401.04125 · PINN sparse-station reconstruction https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11308984/ · DeepXDE https://github.com/lululxvi/deepxde
- **Pros:** Physics consistency; data-efficient; great for sparse-obs fusion. **Cons:** Hard to train (loss balancing, stiffness); scales poorly to full 3D atmosphere.

> NeuralGCM (#7) is the flagship **hybrid ML+numerical** model and is catalogued under FOUNDATION.

---

## 4. GENERATIVE & DOWNSCALING (beyond CorrDiff/NowcastNet/DGMR)

### 32. DeepSD (Vandal et al., KDD 2017)
- **Category:** GEN (stacked SRCNN).
- **What it does:** Stacked super-resolution CNNs with multi-scale (incl. elevation) inputs for statistical downscaling of precipitation.
- **Best use here:** Simple, proven **downscaling baseline** (e.g., 1°→0.125°) to anchor more complex SR/diffusion models; easy to implement.
- **Data needs:** Coarse + high-res pairs + topography.
- **Skill:** Outperformed BCSD for precip downscaling over CONUS; foundational deep-downscaling method.
- **TF/PyTorch:** **TensorFlow** (original) + community ports.
- **Reference/repo:** arXiv https://arxiv.org/abs/1703.03126 · code https://github.com/tjvandal/deepsd
- **Pros:** Simple, interpretable, strong baseline. **Cons:** Deterministic (smooth extremes); dated vs diffusion/GAN.

### 33. SRGAN / ESRGAN / PhIRE-GAN
- **Category:** GEN (adversarial super-resolution).
- **What it does:** GAN-based SR producing realistic high-frequency detail; PhIREGAN tailored to physical fields (wind/solar); ESRGAN improves SRGAN with residual-in-residual dense blocks.
- **Best use here:** Adversarial downscaling of precip/temperature/wind fields with realistic texture and power spectra; cross-check vs CorrDiff/diffusion.
- **Data needs:** Coarse/high-res pairs; GAN training care.
- **Skill:** ESRGAN/PhIREGAN reproduce power-spectral density of winds at 2–5× SR; comparable to dynamical downscaling at ~100× lower cost.
- **TF/PyTorch:** **Both** (BasicSR for ESRGAN; PhIRE TF).
- **Reference/repo:** SRGAN https://arxiv.org/abs/1609.04802 · ESRGAN https://arxiv.org/abs/1809.00219 · PhIRE-GAN https://github.com/NREL/PhIRE
- **Pros:** Sharp, spectrally realistic; fast inference. **Cons:** GAN instability/mode collapse; can hallucinate; weaker calibration than diffusion.

### 34. Diffusion / score-based super-resolution for precipitation
- **Category:** GEN (DDPM / score-based / flow-matching).
- **What it does:** Conditional diffusion (U-Net score network) generates an **ensemble** of plausible high-res fields from coarse input; variants add Wasserstein regularization, wavelet conditioning, video diffusion, and stochastic flow matching.
- **Best use here:** **Stochastic precip downscaling** with calibrated uncertainty — generate many high-res rainfall realizations for extreme-risk estimation; the methodological core of CorrDiff/GenCast.
- **Data needs:** Coarse/high-res pairs (e.g., CPC/ERA5 → km-scale); more compute than GAN/U-Net.
- **Skill:** Best-in-class sharpness + calibration for precip SR; captures heavy-tail extremes better than deterministic SR.
- **TF/PyTorch:** **PyTorch** (PhysicsNeMo; diffusers; research repos).
- **Reference/repo:** Generative diffusion downscaling https://arxiv.org/abs/2404.17752 · score-based + Wasserstein https://arxiv.org/abs/2410.00381 · spatiotemporal video diffusion https://arxiv.org/abs/2312.06071 · wavelet diffusion https://arxiv.org/abs/2507.01354
- **Pros:** Probabilistic, sharp, SOTA for extremes. **Cons:** Sampling cost; needs paired data; tuning noise schedules.

### 35. Normalizing Flows
- **Category:** GEN + UQ (invertible density models).
- **What it does:** Exact-likelihood invertible transforms; can model conditional distributions for probabilistic downscaling/super-resolution and density estimation.
- **Best use here:** Probabilistic downscaling and **distributional bias correction** (map model distribution → obs distribution exactly); calibrated samples for UQ.
- **Data needs:** Paired/aligned data; careful architecture (coupling layers).
- **Skill:** Good calibrated densities; SRFlow-style models competitive for SR; less common than diffusion in recent SOTA.
- **TF/PyTorch:** **Both** (nflows, FrEIA, TF-Probability).
- **Reference/repo:** RealNVP https://arxiv.org/abs/1605.08803 · Glow https://arxiv.org/abs/1807.03039 · SRFlow https://arxiv.org/abs/2006.14200
- **Pros:** Exact likelihood; principled UQ; invertible. **Cons:** Architecturally constrained; can underperform diffusion on sharpness; heavier memory.

---

## 5. CLASSICAL / TABULAR ML & STATISTICS

### 36. XGBoost
- **Category:** CLASSICAL (gradient-boosted trees).
- **What it does:** Regularized gradient boosting; handles nonlinear tabular relationships, missing values, mixed features.
- **Best use here:** **Primary tabular baseline** for station rainfall/temperature from engineered features (lags, climatology, ENSO/IOD/MJO indices, elevation); excellent for **bias correction** (predict obs−model residual) and feature-importance insight.
- **Data needs:** Tabular feature matrix; CPU-friendly.
- **Skill:** In Indian studies, XGBoost **outperformed ARIMA/SVM/ANN/RF** for nonlinear rainfall patterns; ~94% vs 91% (LightGBM) in a multiclass rain study.
- **TF/PyTorch:** Standalone (`xgboost`), GPU-capable; pairs with both DL stacks.
- **Reference/repo:** https://arxiv.org/abs/1603.02754 · https://github.com/dmlc/xgboost
- **Pros:** Fast, accurate, robust, interpretable; tiny compute; strong India track record. **Cons:** Not spatial/sequential natively (needs feature engineering); poor extrapolation beyond training range.

### 37. LightGBM
- **Category:** CLASSICAL (histogram gradient boosting).
- **What it does:** Leaf-wise, histogram-based GBM; very fast on large/high-dimensional tabular data.
- **Best use here:** Same roles as XGBoost but faster on big feature sets / many stations; quantile objective for probabilistic temperature/rain.
- **Data needs:** Tabular; CPU/GPU.
- **Skill:** Near-XGBoost accuracy, faster training; great for large pipelines.
- **TF/PyTorch:** Standalone (`lightgbm`).
- **Reference/repo:** NeurIPS 2017 https://papers.nips.cc/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html · https://github.com/microsoft/LightGBM
- **Pros:** Very fast; quantile loss; memory-efficient. **Cons:** Leaf-wise can overfit small data; same non-spatial caveat.

### 38. CatBoost
- **Category:** CLASSICAL (ordered boosting).
- **What it does:** GBM with native categorical handling and ordered boosting to reduce target leakage; strong out-of-the-box.
- **Best use here:** Tabular baseline when categorical features dominate (station ID, land-use class, season, synoptic regime label); robust default ensemble member.
- **Data needs:** Tabular; CPU/GPU.
- **Skill:** Competitive with XGBoost/LightGBM, often best with minimal tuning.
- **TF/PyTorch:** Standalone (`catboost`).
- **Reference/repo:** https://arxiv.org/abs/1706.09516 · https://github.com/catboost/catboost
- **Pros:** Great defaults; categorical-native; robust. **Cons:** Slower than LightGBM sometimes; non-spatial.

### 39. Random Forest / Gradient Boosting (scikit-learn)
- **Category:** CLASSICAL (bagged/boosted trees).
- **What it does:** RF = bagged decision trees (low variance); GBR = sequential boosting.
- **Best use here:** Robust, low-tuning baselines and **feature-importance** for predictor screening; RF for quick drought/rain classification; cross-checks the boosted-tree members.
- **Data needs:** Tabular; CPU.
- **Skill:** Solid baselines; RF used widely in Indian rainfall studies; usually below XGBoost on nonlinear precip but very stable.
- **TF/PyTorch:** scikit-learn (TF-Decision-Forests also available).
- **Reference/repo:** https://scikit-learn.org/stable/modules/ensemble.html
- **Pros:** Robust, simple, interpretable; minimal tuning. **Cons:** Lower ceiling than boosting; large memory for big RF; non-spatial.

### 40. SVR / Gaussian Process Regression / Kriging
- **Category:** CLASSICAL + UQ (kernel methods).
- **What it does:** SVR = kernel regression; GPR/Kriging = Bayesian non-parametric regression giving **predictive variance**; Kriging is GPR for spatial interpolation.
- **Best use here:** **Spatial interpolation/fusion** of sparse station data to grids with uncertainty (Kriging); small-data UQ; GPR as a calibrated low-data member; SVR as a classic nonlinear baseline.
- **Data needs:** Small/medium datasets (GP scales O(n³)); spatial coordinates for Kriging.
- **Skill:** Excellent interpolation + calibrated UQ on modest data; analog method "performs as well as CCA/NN" for downscaling per literature.
- **TF/PyTorch:** scikit-learn, GPyTorch (PyTorch), GPflow (TF), PyKrige.
- **Reference/repo:** GPR (Rasmussen & Williams) https://gaussianprocess.org/gpml/ · GPyTorch https://github.com/cornellius-gp/gpytorch · PyKrige https://github.com/GeoStat-Framework/PyKrige
- **Pros:** Built-in uncertainty; strong spatial interpolation; principled. **Cons:** Poor scaling to large n (needs sparse/variational GPs); kernel choice sensitive.

### 41. ARIMA / SARIMA / SARIMAX & Prophet
- **Category:** CLASSICAL (statistical time series).
- **What it does:** (S)ARIMA(X) model autocorrelation/seasonality (+exogenous regressors); Prophet = decomposable trend+seasonality+holidays, robust to gaps/outliers.
- **Best use here:** **Mandatory classical baselines** for station temperature/rainfall (strong annual/monsoon seasonality); SARIMAX ingests exogenous indices (ENSO/IOD); Prophet for quick, robust seasonal baselines and missing-data resilience.
- **Data needs:** Single/related series; very light compute.
- **Skill:** Good for linear/seasonal structure; **beaten by XGBoost/ML on nonlinear rainfall** (per Indian studies) — but essential reference floor.
- **TF/PyTorch:** statsmodels (SARIMAX), `prophet`, pmdarima, Darts.
- **Reference/repo:** statsmodels SARIMAX https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html · Prophet https://facebook.github.io/prophet/
- **Pros:** Interpretable, fast, well-understood; great floors. **Cons:** Linear/limited nonlinearity; weak on convective extremes; univariate-centric.

### 42. Quantile Regression / Quantile Regression Forests / EMOS
- **Category:** UQ + CLASSICAL.
- **What it does:** Predict conditional **quantiles** (intervals) rather than the mean; EMOS (Ensemble Model Output Statistics, a.k.a. NGR) is the standard **distributional post-processing** of ensembles (bias + spread calibration via min-CRPS).
- **Best use here:** Turn any point model into probabilistic; **calibrate the ensemble** (Section 13) — EMOS/NGR on rainfall (often censored-shifted-Gamma) and temperature (Gaussian) is the proven post-processor; GBMs (LightGBM) support pinball loss directly.
- **Data needs:** Forecast–obs pairs (training window) for post-processing.
- **Skill:** EMOS reliably improves CRPS over raw ensembles; DL post-processors can beat EMOS but EMOS is the robust default.
- **TF/PyTorch:** statsmodels QuantReg; scikit-garden/quantile-forest; EMOS via `ensembleMOS` (R) or custom min-CRPS in Python.
- **Reference/repo:** EMOS (Gneiting et al. 2005) https://journals.ametsoc.org/view/journals/mwre/133/5/mwr2904.1.xml · DL post-processing review https://royalsocietypublishing.org/doi/10.1098/rsta.2020.0092
- **Pros:** Calibrated intervals; cheap; operational standard. **Cons:** EMOS assumes a parametric form; per-variable tuning.

### 43. Analog Ensemble (AnEn)
- **Category:** CLASSICAL + UQ.
- **What it does:** For a given forecast, find the most similar past forecasts ("analogs") and use their verifying observations to build a probabilistic prediction.
- **Best use here:** Cheap, training-light **probabilistic post-processing / downscaling** for temperature & rainfall using IMDAA history; strong when a long reanalysis archive exists (it does for India via IMDAA/ERA5).
- **Data needs:** Long archive of forecasts + matching obs.
- **Skill:** Competitive with more complex post-processing; "as good as CCA/NN" for many downscaling tasks; excellent cost/skill ratio.
- **TF/PyTorch:** Lightweight custom; `PyAnEn`, AnalogEnsemble libraries.
- **Reference/repo:** Delle Monache et al. 2013 (Mon. Wea. Rev.) https://journals.ametsoc.org/view/journals/mwre/141/10/mwr-d-12-00281.1.xml
- **Pros:** Simple, robust, probabilistic, interpretable. **Cons:** Needs long archive; struggles with unprecedented extremes (no analog).

### 44. EOF/PCA & Self-Organizing Maps (SOM)
- **Category:** CLASSICAL (dimensionality reduction / clustering).
- **What it does:** **EOF/PCA** decomposes spatiotemporal fields into dominant modes (e.g., monsoon variability patterns); **SOM** clusters atmospheric states into a 2D map of synoptic regimes.
- **Best use here:** (1) **Feature/predictor compression** feeding GBMs/LSTMs; (2) **regime-aware fusion** — condition downscaling/bias-correction on SOM regime; (3) SOM-based **statistical downscaling & bias correction** of rainfall (documented for extended-range forecasts); (4) drought/monsoon variability diagnostics.
- **Data needs:** Gridded reanalysis fields.
- **Skill:** SOM bias-correction/downscaling proven for Indian extended-range rainfall; EOF standard in monsoon diagnostics.
- **TF/PyTorch:** scikit-learn (PCA), `eofs` (climate EOF), MiniSom/`susi` (SOM).
- **Reference/repo:** eofs https://ajdawson.github.io/eofs/ · SOM downscaling/bias-correction (Climate Dynamics) https://link.springer.com/article/10.1007/s00382-016-3214-4 · SOM rainfall downscaling (Tellus A) https://www.tandfonline.com/doi/full/10.3402/tellusa.v68.29293
- **Pros:** Interpretable patterns; cheap; great for regime conditioning & monsoon analysis. **Cons:** Linear (EOF) / heuristic (SOM); preprocessing rather than end-to-end predictors.

---

## 6. UNCERTAINTY / ENSEMBLE & SELF-SUPERVISED

### 45. Deep Ensembles / MC-Dropout / Bayesian NNs / Conformal Prediction
- **Category:** UQ (applies across the whole stack).
- **What it does:**
  - **Deep Ensembles:** train N nets (random seeds/data) → predictive mean + variance (the simplest, strongest DL UQ).
  - **MC-Dropout:** keep dropout at inference → Monte-Carlo samples (cheap approximate Bayesian UQ).
  - **Bayesian NNs:** distributions over weights (variational/SWAG) → principled UQ.
  - **Conformal Prediction:** distribution-free intervals with **guaranteed coverage**, applied as online post-processing on top of any model (incl. AI weather ensembles).
- **Best use here:** Wrap **every** member (ConvLSTM, U-Net, GBMs, diffusion) to produce calibrated uncertainty; conformal gives coverage guarantees for decision-making (flood/heat thresholds); deep ensembles are the practical default; recent work links Bayesian DL to weather ensembles.
- **Data needs:** Calibration/holdout set (conformal); multiple trainings (deep ensembles).
- **Skill:** Deep ensembles → best accuracy+UQ trade-off; conformal → guaranteed coverage with no skill loss (shown on AI weather forecasts); MC-dropout cheap but less calibrated.
- **TF/PyTorch:** **Both** (Laplace-torch, TorchUncertainty, MAPIE/`crepes` for conformal, TF-Probability).
- **Reference/repo:** Deep Ensembles (Lakshminarayanan 2017) https://arxiv.org/abs/1612.01474 · MC-Dropout (Gal 2016) https://arxiv.org/abs/1506.02142 · Conformal for AI weather https://arxiv.org/abs/2506.19642 · MAPIE https://github.com/scikit-learn-contrib/MAPIE
- **Pros:** Turns point models probabilistic; conformal has formal guarantees; deep ensembles simple+strong. **Cons:** Deep ensembles cost N×; BNNs hard to scale; MC-dropout under-calibrated; conformal needs exchangeability care for time series (use blocked/adaptive variants).

> **Self-supervised / transfer (cross-cutting):** the foundation models above (ClimaX #5, Aurora #6, Prithvi WxC #11) are **pretrained via self-supervised objectives** (masked reconstruction / masked autoencoding) and are **fine-tuned** for PS5 tasks. For satellite-image fusion, **Prithvi-EO-2.0 / SatMAE** (masked autoencoders for EO) provide pretrained encoders to embed INSAT/Sentinel imagery as features. Refs: Prithvi-EO-2.0 https://arxiv.org/abs/2412.02732 · SatMAE https://arxiv.org/abs/2207.08051. This is the **SSL/transfer** family the mandate asks for.

---

## 13. RECOMMENDED MODEL STACK FOR THE PoC (implement these first)

Given limited hackathon time and modest hardware, implement a **small, complementary stack** that already constitutes a cross-verifying ensemble, then expand. Priorities: fast training, strong baselines, one downscaler, one probabilistic head, one combiner.

**Tier 1 — build first (5 models):**
1. **XGBoost (or LightGBM) tabular baseline** (#36/#37) — per-station/grid-cell rainfall + temperature from engineered features (lags, climatology, ENSO/IOD/MJO, elevation). *Why:* trains in minutes on CPU, very strong on Indian rainfall, gives feature importance + a hard-to-beat floor, and doubles as a **bias-corrector** (predict obs−model residual). Add **quantile/pinball loss** for free probabilistic intervals.
2. **ConvLSTM field nowcaster** (#17) — 0–6 h (extendable) rainfall & temperature fields over the pilot grid (IMD 0.25° rain + ERA5 temp + INSAT). *Why:* the canonical, well-supported (`ConvLSTM2D` in Keras) spatiotemporal baseline with strong Indian precedent; trains on a single GPU.
3. **U-Net downscaler / bias-corrector** (#21) — map coarse (ERA5/IMDAA/GraphCast) → high-res rainfall/temperature; also serves bias correction (model→obs). *Why:* fast, stable, reusable for two PS5 tasks (downscaling + bias correction) on modest hardware. (Upgrade path: swap the U-Net for **CorrDiff/diffusion** (#34/#12) once paired high-res data is ready, to sharpen extremes.)
4. **A classical statistical baseline — SARIMAX + Analog Ensemble** (#41 + #43) — per-station seasonal forecasts with exogenous indices, plus a cheap probabilistic post-processor from the IMDAA archive. *Why:* near-zero compute, interpretable reference floor, and AnEn instantly makes any member probabilistic.
5. **Ensemble combiner: stacked generalization + EMOS** (#42, Section 14) — a meta-learner (ridge/LightGBM) that blends members into a consensus, then EMOS/conformal for calibrated probabilistic output. *Why:* the whole point of the mandate — robust consensus that cross-verifies members and yields calibrated uncertainty.

**Tier 2 — add if time/hardware allow (high value):**
6. **A pretrained foundation model via Earth2Studio** (#16) running **FourCastNet/SFNO + Pangu** (fast, ONNX/PyTorch) and/or **GraphCast** for global large-scale forcing → feed Tier-1 downscaler. *Why:* injects global physics priors with **no training** (inference-only).
7. **ClimODE** (#30) — physics-informed, single-GPU-trainable, uncertainty-aware member that cross-checks pure-ML members.
8. **Fine-tune ClimaX or Prithvi WxC** (#5/#11) for regional forecast/downscaling if GPUs and time permit (open weights; best long-term path).
9. **DGMR or NowcastNet** (#14/#13) for extreme-precip nowcasting if radar/INSAT sequences are available.
10. **TFT or PatchTST** (#25/#27) for interpretable multi-horizon station forecasts + native quantiles.

**Reasoning summary:** Tier 1 covers all five PS5 tasks (forecast, nowcast, downscale, fuse, bias-correct) with **fast-training** models on **modest hardware**, gives at least 3 mutually-independent method families (trees, conv-recurrent, encoder-decoder CNN, classical stats) plus a combiner, and degrades gracefully. Tier 2 adds global physics priors and generative sharpness once the pipeline works end-to-end.

---

## 14. CROSS-VALIDATION & ENSEMBLE FUSION DESIGN (combining 30+ methods)

**Why an ensemble of diverse methods.** Each family has complementary failure modes: trees extrapolate poorly but are robust on tabular signals; conv-recurrent nets blur extremes but capture motion; diffusion/GAN add sharp extremes but can hallucinate; foundation models bring global physics but are coarse; classical stats anchor seasonality. Blending them reduces variance and bias and lets methods **fill each other's gaps**.

**A. How members fill gaps (deliberate diversity):**
- *Trees (XGBoost/LightGBM/CatBoost)* → strong on point/station signals & nonlinear predictor interactions; bias-correction residuals.
- *Conv-recurrent (ConvLSTM/TrajGRU/PredRNN)* → spatial fields & motion (nowcasting).
- *Generative (CorrDiff/diffusion/DGMR/NowcastNet)* → sharp extremes & calibrated stochastic detail at high res.
- *Foundation (GraphCast/Pangu/FourCastNet/GenCast)* → global large-scale state & long lead; provide boundary forcing and an independent "opinion."
- *Physics/hybrid (NeuralGCM/ClimODE/PINNs)* → physical consistency & conservation; sanity bounds.
- *Classical (SARIMAX/Prophet/AnEn/GPR)* → seasonality, interpretable floor, spatial interpolation with UQ.

**B. Fusion methods (consensus engines):**
1. **Stacked generalization (super-learner)** — train a meta-model (ridge/elastic-net for stability, or LightGBM for nonlinear blending) on **out-of-fold** base predictions. Use **out-of-fold predictions only** to avoid leakage. Robust default; can learn per-regime weights if SOM-regime is a meta-feature.
2. **Bayesian Model Averaging (BMA)** — weight members by posterior performance; yields a predictive **distribution** (good for rainfall PDFs). Classic for weather ensembles (Raftery et al.).
3. **Weighted ensembles / performance-based weights** — inverse-error or CRPS-optimal weights; simple and strong; "stacking of predictive distributions" generalizes BMA.
4. **EMOS / NGR on the multi-model ensemble** — calibrate the *combined* ensemble's mean and spread against obs (min-CRPS); the operational standard for the final probabilistic product.
5. **Regime/space conditioning** — let weights vary by SOM synoptic regime, season (monsoon vs non-monsoon), or sub-region, since member skill is state-dependent.
6. **Conformal calibration on top** — wrap the fused predictive intervals to guarantee coverage for threshold decisions.

**C. Cross-validation that respects space & time (critical):**
- **Do NOT use random k-fold** on spatiotemporal data — autocorrelation leaks and *understates* error (random splits overstated/understated errors by up to 70–80% vs spatially-blocked alternatives in the literature). Use:
  - **Rolling/expanding-window (forward-chaining) CV** for temporal generalization (train past → test future).
  - **Spatially-blocked CV** (hold out contiguous regions, block ≥ spatial autocorrelation range) to test spatial transfer.
  - **Leave-one-monsoon-season-out / leave-one-year-out** to test inter-annual generalization (monsoon variability).
  - **Buffer/embargo** gaps between train and test blocks to remove leakage at boundaries.
- **Nested CV** for the stack: inner folds tune base models + meta-learner weights (on out-of-fold preds), outer folds give an **honest** estimate of fused-ensemble skill.
- **Always report against persistence + climatology + at least one NWP/FM baseline** (e.g., IMD operational, ERA5-driven GraphCast) for skill scores.

**Refs:** stacking predictive distributions (Yao et al.) https://projecteuclid.org/journals/bayesian-analysis/volume-13/issue-3/Using-Stacking-to-Average-Bayesian-Predictive-Distributions-with-Applications/10.1214/17-BA1091.full · BMA for ensembles (Raftery et al. 2005) https://journals.ametsoc.org/view/journals/mwre/133/5/mwr2906.1.xml · spatiotemporal CV https://www.mdpi.com/2227-7390/9/6/691 · blocked CV review https://arxiv.org/abs/2402.00183

---

## 15. EVALUATION METRICS (rainfall + temperature)

**Deterministic (temperature, continuous):**
- **RMSE** — penalizes large errors (sensitive to extremes); primary temperature metric.
- **MAE** — robust average error.
- **Bias (ME)** — systematic over/under-prediction; key for bias-correction validation.
- **Anomaly Correlation Coefficient (ACC)** — pattern skill vs climatology (standard in NWP).
- **R² / Pearson r** — explained variance / correlation.

**Precipitation categorical (per threshold, e.g., 1, 2.5, 7.5, 15, 35, 64.5 mm/day per IMD classes):** from the 2×2 contingency table (hits H, misses M, false alarms F):
- **POD (Probability of Detection)** = H/(H+M).
- **FAR (False Alarm Ratio)** = F/(H+F).
- **CSI / Threat Score** = H/(H+M+F) — the headline precip skill score.
- **ETS (Equitable Threat Score)** — CSI adjusted for random hits (fairer across thresholds).
- **Frequency Bias** = (H+F)/(H+M) — over/under-forecasting frequency.
- **HSS / Heidke Skill Score** — skill vs random.

**Spatial / field quality:**
- **FSS (Fractions Skill Score)** — neighborhood-based; rewards "close enough" precip (avoids the double-penalty problem); report across scales & thresholds. **The key spatial precip metric.**
- **SSIM (Structural Similarity)** — structural realism of predicted fields (textures, gradients) — useful for downscaling/generative outputs.
- **PSNR** — pixel-level field fidelity (downscaling).
- **Power-spectral-density / spectral skill** — does the (downscaled) field have realistic small-scale variance? (catches GAN/diffusion over-/under-sharpening).

**Probabilistic / ensemble:**
- **CRPS (Continuous Ranked Probability Score)** — headline probabilistic score (generalizes MAE); lower is better; used to optimize EMOS and compare ensembles (e.g., GenCast's CRPS gains).
- **CRPSS** — CRPS skill score vs reference.
- **Brier Score / BSS** — probabilistic skill for binary events (e.g., P(rain>35 mm)).
- **Reliability diagrams & rank (Talagrand) histograms** — calibration & ensemble spread (flat histogram = well-dispersed).
- **Spread–skill ratio** — is ensemble spread ≈ error? (target ≈ 1).
- **Quantile/pinball loss** — for quantile-regression outputs.
- **Coverage / interval width** — for conformal prediction (target coverage met at minimal width).

**Extremes & drought (project-specific):**
- **Extremal Dependence Index (EDI/SEDI)** — base-rate-independent skill for rare events (better than CSI for extremes).
- **Heavy-rain CSI/FSS at high thresholds**, **peak-over-threshold** statistics.
- **Drought indices verification** — SPI/SPEI correlation, onset/duration error.

> Validate on **WeatherBench 2** conventions where global comparability helps (https://github.com/google-research/weatherbench2), but use **IMD thresholds + station verification** for the India pilot. Report metrics **stratified** by season (monsoon/non-monsoon), region, and lead time.

---

## 16. DATA ASSIMILATION × ML — the ML hooks (deep detail deferred to the DA doc)

The digital twin needs to **ingest live, heterogeneous observations** (AWS/ARG stations, INSAT-3D/3DR radiances, GPM/IMERG, DWR radar). DA is how observations correct model state. Note these **ML hooks** now; full DA design lives in the dedicated DA document.

- **Densification / implicit DA in one network (MetNet-3 style, #15):** train a single net to consume sparse station obs + dense satellite/radar and emit dense analyzed fields — the simplest "ML-as-DA" pattern and a strong fit for PS5 fusion. Hook: a fusion encoder that treats observations as additional input channels/tokens.
- **Latent-space DA (autoencoder/VAE + EnKF):** learn a low-dim latent with an autoencoder, run **Ensemble Kalman Filter** updates in latent space (cheaper, physically-consistent reconstructions). Recent results show physically-consistent global atmospheric DA in latent space. Hook: our U-Net/ViT encoders can provide the latent; couple to an EnKF.
  - Refs: latent-space ML DA (Science Advances 2025) https://www.science.org/doi/10.1126/sciadv.aea4248 · VAE + EnKF https://arxiv.org/abs/2502.12987
- **AI-model + variational DA (FengWu-4DVar, #9):** couple a data-driven forecaster with **4D-Var** so the AI model's differentiability provides cheap adjoints. Hook: any differentiable PyTorch forecaster (ClimODE, U-Net, ClimaX) can serve as the forward model for variational/learned DA.
  - Ref: FengWu-4DVar https://arxiv.org/abs/2312.12455
- **Diffusion/score-based DA (SDA, DAISI, DAISI-style interpolants):** use a learned generative prior as the background term and condition on observations — turns the diffusion downscaler (#34) into an assimilation engine. Hook: condition CorrDiff/diffusion on observation likelihoods.
- **End-to-end learned observation operators:** NN surrogates mapping model state → satellite radiances (INSAT) so raw radiances can be assimilated/fused without hand-built RTMs. Hook: train a small ResNet/MLP observation operator.
- **Survey for grounding:** convergence of ML and DA in Earth-system science (Nature npj AI 2026) https://www.nature.com/articles/s44387-026-00107-0 · hybrid ML-DA system https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2022.1012165/full

**Minimum viable DA-ML for the PoC:** start with the **MetNet-3-style fusion network** (observations as input channels) — it captures the *benefit* of DA (obs-aware dense fields) without a full assimilation cycle — then graduate to latent-space EnKF or FengWu-4DVar-style coupling in the full twin.

---

## 17. Quick mapping — method families → PS5 tasks

| PS5 task | First choice (PoC) | Strong alternatives / cross-checks |
|----------|--------------------|-------------------------------------|
| **Rainfall forecast (short-term)** | ConvLSTM (#17) + XGBoost (#36) | TrajGRU/PredRNN (#18/#19), Pangu/GraphCast forcing (#2/#1), TFT/PatchTST (#25/#27) |
| **Temperature forecast** | XGBoost/LightGBM (#36/#37) + ConvLSTM (#17) | TFT (#25), SARIMAX (#41), ClimODE (#30), foundation FMs |
| **Nowcasting (0–3 h precip)** | ConvLSTM/TrajGRU (#17/#18) | NowcastNet (#13), DGMR (#14), MetNet-3 (#15) |
| **Downscaling / super-resolution** | U-Net (#21) → CorrDiff (#12) | DeepSD (#32), ESRGAN (#33), diffusion SR (#34), Prithvi WxC (#11) |
| **Data fusion (multi-source)** | MetNet-3-style net (#15) | Prithvi-EO/SatMAE features (#11/SSL), Kriging (#40), GNNs (#28/#29) |
| **Bias correction** | XGBoost residual (#36) + U-Net (#21) | Quantile mapping + DL, EMOS (#42), normalizing flows (#35) |
| **Monsoon variability / regimes** | EOF/PCA + SOM (#44) | FuXi sub-seasonal (#10), SARIMAX+indices (#41) |
| **Extremes** | Diffusion/CorrDiff (#34/#12), NowcastNet (#13) | GenCast (#4), conformal UQ (#45), EDI/FSS metrics |
| **Drought / seasonal context** | SARIMAX+indices (#41), AnEn (#43) | NeuralGCM/FuXi (#7/#10), SPI/SPEI verification |
| **Uncertainty (all tasks)** | Deep ensembles + EMOS + conformal (#45/#42) | BMA, quantile regression, GPR |
| **Consensus / fusion** | Stacking + EMOS (#13–14) | BMA, weighted/regime-conditioned ensembles |

---

## Sources (primary)

GraphCast: https://www.science.org/doi/10.1126/science.adi2336 · https://github.com/google-deepmind/graphcast
Pangu-Weather: https://www.nature.com/articles/s41586-023-06185-3 · https://github.com/198808xc/Pangu-Weather
FourCastNet: https://arxiv.org/abs/2208.05419 · https://github.com/NVlabs/FourCastNet
GenCast: https://arxiv.org/abs/2312.15796 · https://deepmind.google/blog/gencast-predicts-weather-and-the-risks-of-extreme-conditions-with-sota-accuracy/
ClimaX: https://arxiv.org/abs/2301.10343 · https://github.com/microsoft/ClimaX
Aurora: https://arxiv.org/abs/2405.13063 · https://github.com/microsoft/aurora
NeuralGCM: https://www.nature.com/articles/s41586-024-07744-y · https://github.com/google-research/neuralgcm
Stormer: https://arxiv.org/abs/2312.03876
FengWu: https://arxiv.org/abs/2304.02948 · https://github.com/OpenEarthLab/ai-models-fengwu
FuXi: https://arxiv.org/abs/2306.12873 · https://github.com/tpys/FuXi
Prithvi WxC: https://arxiv.org/abs/2409.13598 · https://huggingface.co/ibm-nasa-geospatial/Prithvi-WxC-1.0-2300M · https://github.com/NASA-IMPACT/Prithvi-WxC
CorrDiff: https://arxiv.org/abs/2309.15214 · https://www.nature.com/articles/s43247-025-02042-5
NowcastNet: https://www.nature.com/articles/s41586-023-06184-4
DGMR: https://www.nature.com/articles/s41586-021-03854-z · https://github.com/openclimatefix/skillful_nowcasting
MetNet-3: https://arxiv.org/abs/2306.06079
Earth2Studio: https://github.com/NVIDIA/earth2studio · https://nvidia.github.io/earth2studio/
ConvLSTM: https://arxiv.org/abs/1506.04214
TrajGRU: https://arxiv.org/abs/1706.03458
PredRNN/++: https://arxiv.org/abs/2103.09504 · https://arxiv.org/abs/1804.06300
E3D-LSTM: https://openreview.net/forum?id=B1lKS2AqtX
U-Net / U-Net++: https://arxiv.org/abs/1505.04597 · https://arxiv.org/abs/1807.10165
ResNet: https://arxiv.org/abs/1512.03385
ViT: https://arxiv.org/abs/2010.11929
Swin / Swin-Unet / SwinUNETR: https://arxiv.org/abs/2103.14030 · https://arxiv.org/abs/2105.05537 · https://arxiv.org/abs/2201.01266
TFT: https://arxiv.org/abs/1912.09363
Informer/Autoformer/FEDformer: https://arxiv.org/abs/2012.07436 · https://arxiv.org/abs/2106.13008 · https://arxiv.org/abs/2201.12740
PatchTST: https://arxiv.org/abs/2211.14730 · https://github.com/yuqinie98/PatchTST
Graph WaveNet: https://arxiv.org/abs/1906.00121
STGCN: https://arxiv.org/abs/1709.04875
ClimODE: https://arxiv.org/abs/2404.10024 · https://github.com/Aalto-QuML/ClimODE
PINNs/DeepPhysiNet: https://arxiv.org/abs/2401.04125 · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11308984/ · https://github.com/lululxvi/deepxde
DeepSD: https://arxiv.org/abs/1703.03126 · https://github.com/tjvandal/deepsd
SRGAN/ESRGAN/PhIRE: https://arxiv.org/abs/1609.04802 · https://arxiv.org/abs/1809.00219 · https://github.com/NREL/PhIRE
Diffusion downscaling: https://arxiv.org/abs/2404.17752 · https://arxiv.org/abs/2410.00381 · https://arxiv.org/abs/2312.06071
Normalizing flows: https://arxiv.org/abs/1605.08803 · https://arxiv.org/abs/1807.03039 · https://arxiv.org/abs/2006.14200
XGBoost: https://arxiv.org/abs/1603.02754 · https://github.com/dmlc/xgboost
LightGBM: https://github.com/microsoft/LightGBM
CatBoost: https://arxiv.org/abs/1706.09516 · https://github.com/catboost/catboost
RF/GBR: https://scikit-learn.org/stable/modules/ensemble.html
GPR/Kriging: https://gaussianprocess.org/gpml/ · https://github.com/cornellius-gp/gpytorch · https://github.com/GeoStat-Framework/PyKrige
SARIMAX/Prophet: https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html · https://facebook.github.io/prophet/
EMOS: https://journals.ametsoc.org/view/journals/mwre/133/5/mwr2904.1.xml
Analog Ensemble: https://journals.ametsoc.org/view/journals/mwre/141/10/mwr-d-12-00281.1.xml
EOF (eofs): https://ajdawson.github.io/eofs/ · SOM downscaling: https://link.springer.com/article/10.1007/s00382-016-3214-4
Deep Ensembles / MC-Dropout / Conformal: https://arxiv.org/abs/1612.01474 · https://arxiv.org/abs/1506.02142 · https://arxiv.org/abs/2506.19642
Prithvi-EO-2.0 / SatMAE: https://arxiv.org/abs/2412.02732 · https://arxiv.org/abs/2207.08051
WeatherBench 2: https://github.com/google-research/weatherbench2 · https://arxiv.org/abs/2308.15560
India monsoon DL: https://www.nature.com/articles/s41598-023-44284-3 · https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.70023 · ConvLSTM Indian cities https://arxiv.org/abs/2511.11152
India data (IMDAA): https://journals.ametsoc.org/view/journals/clim/34/12/JCLI-D-20-0412.1.xml · IMD merged rainfall https://rcc.imdpune.gov.in/download.php
Bias correction DL: https://arxiv.org/abs/2504.19145 · https://link.springer.com/article/10.1007/s00382-024-07406-9
DA × ML: https://www.science.org/doi/10.1126/sciadv.aea4248 · https://arxiv.org/abs/2502.12987 · https://arxiv.org/abs/2312.12455 · https://www.nature.com/articles/s44387-026-00107-0
Ensemble fusion / CV: https://journals.ametsoc.org/view/journals/mwre/133/5/mwr2906.1.xml · https://projecteuclid.org/journals/bayesian-analysis/volume-13/issue-3/Using-Stacking-to-Average-Bayesian-Predictive-Distributions-with-Applications/10.1214/17-BA1091.full · https://www.mdpi.com/2227-7390/9/6/691
