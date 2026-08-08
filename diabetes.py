import sqlite3
import statistics
import streamlit as st
from typing import Dict, List, Optional, Tuple

# =====================================================================
# 1. DATA ACCESS LAYER (SQLite Database)
# =====================================================================
class PatientModel:
    """Manages persistent patient data storage using SQLite."""
    
    def __init__(self, db_path='diabetes_patients.db'):
        self.db_path = db_path
        self._init_db()
        self._seed_and_clean_data()

    def _get_connection(self):
        # check_same_thread=False is required for Streamlit's threading model
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        """Creates the database table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY,
                    Glucose REAL,
                    BMI REAL,
                    Age REAL,
                    BloodPressure REAL
                )
            ''')
            conn.commit()

    def _seed_and_clean_data(self):
        """Seeds initial data if empty, and imputes invalid BMI values."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM patients")
            
            # Seed data if DB is completely empty
            if cursor.fetchone()[0] == 0:
                initial_data = [
                    (101, 95.0, 22.5, 28.0, 115.0),
                    (102, 145.0, 0.0, 54.0, 135.0),
                    (103, 112.0, 29.1, 42.0, 122.0),
                    (104, 180.0, 36.4, 61.0, 142.0)
                ]
                cursor.executemany('''
                    INSERT INTO patients (id, Glucose, BMI, Age, BloodPressure)
                    VALUES (?, ?, ?, ?, ?)
                ''', initial_data)
                conn.commit()

            # Clean initial data (Impute BMI <= 0 with median of valid BMIs)
            cursor.execute("SELECT BMI FROM patients WHERE BMI > 0")
            valid_bmis = [row[0] for row in cursor.fetchall()]
            median_bmi = statistics.median(valid_bmis) if valid_bmis else 25.0
            
            cursor.execute("UPDATE patients SET BMI = ? WHERE BMI <= 0", (round(median_bmi, 1),))
            conn.commit()

    def get_all_ids(self) -> List[int]:
        """Retrieves all registered patient IDs."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT id FROM patients ORDER BY id")
            return [row[0] for row in cursor.fetchall()]

    def get_patient(self, patient_id: int) -> Optional[Dict[str, float]]:
        """Retrieves a specific patient's metrics from the database."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT Glucose, BMI, Age, BloodPressure FROM patients WHERE id = ?", 
                (patient_id,)
            )
            row = cursor.fetchone()
            if row:
                return {"Glucose": row[0], "BMI": row[1], "Age": row[2], "BloodPressure": row[3]}
            return None

    def update_patient(self, patient_id: int, updated_metrics: Dict[str, float]) -> bool:
        """Updates a specific patient's metrics in the database."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT id FROM patients WHERE id = ?", (patient_id,))
            if cursor.fetchone():
                conn.execute('''
                    UPDATE patients 
                    SET Glucose = ?, BMI = ?, Age = ?, BloodPressure = ?
                    WHERE id = ?
                ''', (
                    updated_metrics["Glucose"], 
                    updated_metrics["BMI"], 
                    updated_metrics["Age"], 
                    updated_metrics["BloodPressure"], 
                    patient_id
                ))
                conn.commit()
                return True
            return False


# =====================================================================
# 2. BUSINESS LOGIC LAYER (SERVICE)
# =====================================================================
class ClinicalRiskService:
    """Handles clinical decision rules, point scoring, and risk categorization."""

    THRESHOLDS = {
        "Glucose": (100.0, 125.0),
        "BMI": (25.0, 29.9),
        "Age": (35.0, 55.0),
        "BloodPressure": (120.0, 130.0)
    }

    def calculate_metric_score(self, metric_name: str, value: float) -> int:
        if metric_name not in self.THRESHOLDS:
            return 0
        low_max, med_max = self.THRESHOLDS[metric_name]
        if value <= low_max:
            return 0
        elif value <= med_max:
            return 1
        return 2

    def evaluate_patient_risk(self, metrics: Dict[str, float]) -> Tuple[int, str]:
        total_score = sum(self.calculate_metric_score(m, v) for m, v in metrics.items())
        if total_score <= 2:
            category = "Low Risk"
        elif total_score <= 5:
            category = "Moderate Risk"
        else:
            category = "High Risk"
        return total_score, category


# =====================================================================
# 3. STREAMLIT APPLICATION (Replaces Console MVC components)
# =====================================================================
def main():
    st.set_page_config(page_title="Diabetes Risk Scoring", layout="centered")
    st.title("🩺 Diabetes Risk Scoring System")
    st.write("Data is now securely stored and read using a persistent SQLite database.")

    # Initialize instances
    @st.cache_resource
    def get_models():
        return PatientModel(), ClinicalRiskService()

    db_model, rules_service = get_models()
    valid_ids = db_model.get_all_ids()

    # Sidebar: Patient Selection
    st.sidebar.header("Patient Selection")
    selected_id_str = st.sidebar.selectbox("Select Patient ID to Assess:", ["-- Select --"] + [str(i) for i in valid_ids])

    if selected_id_str != "-- Select --":
        patient_id = int(selected_id_str)
        patient_metrics = db_model.get_patient(patient_id)

        if not patient_metrics:
            st.error(f"Patient ID {patient_id} does not exist in the database.")
            return

        # Calculate Clinic Averages
        all_patients = [db_model.get_patient(pid) for pid in valid_ids]
        clinic_averages = {}
        for metric in patient_metrics.keys():
            values = [p[metric] for p in all_patients if p and metric in p]
            if values:
                clinic_averages[metric] = sum(values) / len(values)

        # Main Area: Profile & Modification
        st.subheader(f"Patient {patient_id} Clinical Profile")
        
        with st.form("patient_form"):
            st.write("Modify any metrics below and submit to recalculate risk and update the database.")
            
            col1, col2 = st.columns(2)
            updated_metrics = {}
            with col1:
                updated_metrics["Glucose"] = st.number_input("Glucose", value=float(patient_metrics["Glucose"]))
                updated_metrics["BMI"] = st.number_input("BMI", value=float(patient_metrics["BMI"]))
            with col2:
                updated_metrics["Age"] = st.number_input("Age", value=float(patient_metrics["Age"]))
                updated_metrics["BloodPressure"] = st.number_input("BloodPressure", value=float(patient_metrics["BloodPressure"]))

            submit = st.form_submit_button("Save Changes & Assess Risk", type="primary")

        # Process update and calculate score
        if submit:
            db_model.update_patient(patient_id, updated_metrics)
            patient_metrics = updated_metrics
            st.toast(f"Patient {patient_id} successfully updated in database!")

        # Perform risk assessment
        score, category = rules_service.evaluate_patient_risk(patient_metrics)
        abnormal_metrics = [m for m, v in patient_metrics.items() if rules_service.calculate_metric_score(m, v) > 0]

        # Display Report
        st.divider()
        st.subheader("Diagnostic Risk Report")
        
        # Color code the category
        if "High" in category:
            st.error(f"**Risk Category:** {category.upper()} (Score: {score} pts)")
        elif "Moderate" in category:
            st.warning(f"**Risk Category:** {category.upper()} (Score: {score} pts)")
        else:
            st.success(f"**Risk Category:** {category.upper()} (Score: {score} pts)")

        # Detailed breakdown comparing to clinic averages
        st.write("### Clinical Summary & Clinic Averages")
        for metric, val in patient_metrics.items():
            avg = clinic_averages.get(metric, 0)
            comparison = "🔴 ABOVE" if val > avg else "🟢 BELOW" if val < avg else "⚪ EQUAL TO"
            
            # Note if it contributed to risk
            flag = "⚠️ Contributed to Risk" if metric in abnormal_metrics else "✅ Healthy Boundary"
            st.write(f"- **{metric}**: {val} _({comparison} clinic average of {avg:.1f})_ — {flag}")

if __name__ == "__main__":
    main()
