# 🏎️ Formula 1 Finishing Position Prediction  

### 📘 Overview  
This project applies machine learning to **predict Formula 1 driver finishing positions** using historical race data. It explores how factors like **starting grid position**, **driver and constructor performance**, and **track characteristics** influence race outcomes.  

---

### 🧠 Objectives  
- Build regression models to predict **driver finishing positions**.  
- Evaluate feature importance across race, driver, and constructor data.  
- Compare the performance of **Random Forest**, **Linear Regression**, and **Decision Tree** models.  

---

### ⚙️ Methods  
- **Data Preparation:** Cleaned and merged multiple Formula 1 datasets containing race results, circuits, drivers, and constructors.  
- **Feature Engineering:** Encoded categorical variables, created dummy features for tracks, drivers, and constructors, and normalized numerical attributes.  
- **Modeling:**  
  - Trained multiple regression models to predict finishing positions.  
  - Evaluated models using **R² scores**, **MAE**, and **cross-validation**.  
- **Visualization:** Analyzed relationships between grid positions, constructor quality, and race outcomes using scatter plots and correlation heatmaps.  

---

### 📊 Key Findings  
- **Grid position** and **constructor performance** were the strongest predictors of final results.  
- The **Random Forest Regressor** achieved the best accuracy compared to linear and decision tree models.  
- Drivers starting in the top 5 grid spots had a statistically significant advantage across circuits.  

---

### 💻 Tech Stack  
`Python` | `Pandas` | `Scikit-learn` | `Matplotlib` | `Seaborn`  
