PROBLEM STATEMENT 5

AI-Powered Digital Twin of India's Climate using India's National Data
Description
A digital twin of the climate system targeting adaptation is expected to make use of observations, integrate several climate models to consider uncertainty sources, include applications for climate-sensitive sectors directly connected to the climate models, and provide interfaces to configure the simulations, output, and data consumers. An "AI-powered Digital Twin of India's Climate using national datasets" refers to the creation of a high-fidelity, dynamic virtual replica of India's climate system that continuously evolves using real-time and historical observations. This digital twin integrates multi-source data from Indian satellites (e.g., INSAT, Oceansat), ground-based meteorological networks (IMD), reanalysis products, and hydrological datasets to simulate atmospheric, oceanic, and land-surface processes at high spatial and temporal resolution. Leveraging advances in Artificial Intelligence, Machine Learning, and Data Assimilation, the system fuses heterogeneous datasets to generate near-real-time climate states and predictive scenarios. The digital twin can capture complex phenomena such as monsoon variability, extreme, drought evolution with improved accuracy compared to conventional models.

The proposed "AI-Powered Digital Twin of India's Climate" directly aligns with ISRO's vision of leveraging space-based observations, geospatial technologies, and artificial intelligence for societal benefit. By integrating national datasets from ISRO platforms such as Bhuvan, MOSDAC, NICES, and other Earth observation missions, the solution creates a dynamic virtual replica of India's climate system for monitoring, forecasting, and scenario-based analysis. This challenge supports national priorities in climate resilience, disaster risk reduction, water and agricultural security, and sustainable development by enabling data-driven decision-making. It also advances the vision of 'Atmanirbhar Bharat' by developing indigenous AI-powered climate intelligence capabilities using India's own satellite, meteorological, and geospatial datasets, thereby strengthening national preparedness for climate change and extreme weather events.

Objectives
To design and develop a scalable framework for an AI-driven digital twin of India's climate using national datasets (satellite, ground observations, and reanalysis).
To demonstrate the Proof of Concept (PoC) of the digital twin for key climate variables rainfall and temperature, by generating high-resolution analyses and short-term predictions over a selected pilot region.
Interactive geospatial visualization on a map dashboard.
A "what-if" simulation module showing impacts of temperature or rainfall changes
Expected Outcomes
Proof-of-Concept of Digital Twin
AI-based prediction capability
Visualization dash board
Scenario simulation capability
Scalable framework for national deployment
Dataset Required
Rainfall data: https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html
Max Temp. data: https://imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html
Min. Temp. data: https://www.imdpune.gov.in/cmpg/Griddata/Min_1_Bin.html
The India Meteorological Department (IMD) provides high-resolution gridded rainfall and temperature datasets, which are widely used for climate monitoring, trend analysis, and weather prediction studies. These datasets offer long-term historical records with consistent spatial and temporal coverage across India, making them suitable for training AI models and validating forecasts. Further, the integration of IMD gridded datasets with INSAT satellite observations enables the development of a data-driven climate intelligence framework capable of capturing both surface and atmospheric conditions.

The below Table provides detailed information data Collection:

Climate Parameter	Data download source
INSAT Land Surface Temperature (LST)	Product name: 3RIMG_L2B_LST
https://www.mosdac.gov.in/
INSAT Sea Surface Temperature (SST)	Product name: 3RIMG_L2B_SST
https://www.mosdac.gov.in/
INSAT Rainfall	Product name: 3RIMG_L2B_IMC
https://www.mosdac.gov.in/
Ground based gridded rainfall-IMD	Product name: Gridded Rainfall (0.25 x 0.25)
https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html
Ground based gridded Temperature-IMD	Product name: Maximum Temperature (1.0 x 1.0)
https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html
Suggested Tools/Technologies
AI/Machine Learning/Deep learning frameworks (e.g., TensorFlow, PyTorch)
Expected Solution / Steps to be followed to achieve the objectives
The schematic Figure 1 illustrates a streamlined workflow for developing a Proof of Concept (PoC) AI-powered Digital Twin of India's Climate, focusing on rainfall and temperature. It begins with defining the problem and selecting a pilot region, followed by the collection of multi-source national datasets from agencies such as the India Meteorological Department and Indian Space Research Organisation. These datasets are then pre-processed and integrated into a consistent format suitable for modeling. An AI model, built using frameworks like TensorFlow or PyTorch, is trained to generate short-term predictions. The outputs feed into a digital twin simulation that represents the current and future climate state over the selected region. The system is subsequently validated against observations, visualized through interactive dashboards, and extended to scenario-based analysis, enabling users to explore "what-if" climate conditions and derive actionable insights for decision-making.

Evaluation Parameters
Problem Understanding & Clarity
Data Usage & Pre-processing
Model Development & Technical Approach
Prediction Performance & Validation
Digital Twin Concept Implementation
Visualization & User Interface
Innovation & Creativity
Presentation & Communication
Image representing problem statement
Workflow diagram from problem definition and data collection through data processing, model development, training and validation, digital twin simulator, scenario analysis, and visualization
