# AMC Exam Suite

A comprehensive, open-source desktop application designed to streamline academic examination logistics. This suite provides a dual-purpose workspace: a dynamic PDF template generator for creating official examination materials, and an advanced Computer Vision pipeline for high-speed, automated evaluation of scanned OMR (Optical Mark Recognition) sheets.

## Features

### 🖨️ Document Template Generator

* **Batch OMR Generation:** Automatically generate hundreds of customized OMR answer sheets (supporting 50- and 100-question architectures) mapped directly to student data via CSV.
* **Dynamic QR Integration:** Embeds scannable QR codes containing student USN, Name, and Course Code for automated identity harvesting during evaluation.
* **Custom Printouts:** Generate standardized official forms including Computer Aided Drawing (CAED) Printout Sheets and Relieving Superintendent Diaries.
* **Institution Branding:** Supports custom left/right institutional logos and watermark injections for official security.

### 🎯 Computer Vision Evaluator

* **Robust Optical Grading:** Utilizes OpenCV for contour detection, adaptive thresholding, and bubble-fill analysis to grade scanned sheets against a master key matrix.
* **Auto-Alignment (Perspective Warping):** Detects 4-corner structural anchors to dynamically unwarp and flatten misaligned, rotated, or skewed scans.
* **Data Extraction:** Harvests student identity via QR codes (`pyzbar`) and reads the bubbled Question Paper Version Code.
* **Batch Processing & Analytics:** Process large batches of scanned PDFs or images simultaneously, exporting the final calculated scores, confidence metrics, and flagged exceptions directly to a CSV report.

## Tech Stack

* **GUI Framework:** `PySide6` (Qt for Python)
* **Computer Vision:** `opencv-python` (cv2), `pyzbar`
* **PDF Generation:** `reportlab`
* **PDF Processing:** `PyMuPDF` (fitz)
* **Data Management:** `pandas`, `numpy`

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/yourusername/amc-exam-suite.git
cd amc-exam-suite

```

**2. Create and activate a virtual environment**
For macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate

```

*(For Windows: `venv\Scripts\activate`)*

**3. Install dependencies**

```bash
pip install PySide6 opencv-python PyMuPDF reportlab pandas numpy pyzbar

```

*(Note for macOS users: If pyzbar fails to find the zbar shared library, you may need to install it via Homebrew: `brew install zbar`)*

## Usage

Launch the application from your terminal:

```bash
python "AMC_Exam_Suite (6).py"

```

### Workflow Guide

1. **Generation:** Navigate to the "Sheet Template Generator" tab. Upload your institutional logos, a CSV of student details (Columns required: `USN`, `Name`), and define the course code. Click "Generate" to produce a batch PDF ready for printing.
2. **Calibration:** Navigate to the "Computer Vision Evaluator" tab. Upload a master key CSV (Columns: `Question`, `Version_A`, `Version_B`, `Version_C`, `Version_D`). Use the Calibration workspace to test a single scan and adjust the "Sensitivity Filter Threshold" slider until bubble detection is accurate.
3. **Evaluation:** Switch to the Batch Verification Workflow, upload your directory of scanned OMR PDFs/images, and export the final grades to CSV.

## Contributing

Contributions are welcome! If you would like to improve the computer vision accuracy, add new document templates, or optimize the PySide6 UI:

1. Fork the repository.
2. Create a new feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

Any modifications or derivative works distributed or made available over a network must also be open-sourced under the AGPLv3. See the `LICENSE` file for more details.
