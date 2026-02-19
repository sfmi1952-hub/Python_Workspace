import win32com.client
import os

class ConfigLoader:
    def __init__(self):
        self.excel_app = None
        self.wb = None
        self.main_sheet = None

    def load_workbook(self, file_path):
        """
        Opens the Excel workbook in the background.
        """
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Excel file not found: {file_path}")

        try:
            self.excel_app = win32com.client.Dispatch("Excel.Application")
            self.excel_app.Visible = False  # Run in background
            self.wb = self.excel_app.Workbooks.Open(file_path)
            self.main_sheet = self.wb.ActiveSheet # Default to active sheet
        except Exception as e:
            self.close()
            raise e

    def get_range_value(self, range_name, sheet_name=None):
        """
        Gets the value of a named range.
        If sheet_name is provided, looks in that sheet.
        Otherwise, looks in the Workbook global names or ActiveSheet.
        """
        try:
            if sheet_name:
                sheet = self.wb.Sheets(sheet_name)
                return sheet.Range(range_name).Value
            else:
                # Try Application.Range (Global/ActiveSheet)
                return self.excel_app.Range(range_name).Value
        except Exception as e:
            # Fallback: try to find name in Workbook names
            try:
                if sheet_name:
                     return self.wb.Sheets(sheet_name).Range(range_name).Value
                return self.wb.Names(range_name).RefersToRange.Value
            except:
                print(f"Warning: Could not read range '{range_name}' in sheet '{sheet_name}'. {e}")
                return None

    def get_range_object(self, range_name, sheet_name=None):
        """
        Returns the COM Range object itself.
        """
        try:
            if sheet_name:
                return self.wb.Sheets(sheet_name).Range(range_name)
            else:
                return self.excel_app.Range(range_name)
        except Exception as e:
            print(f"Error getting range object '{range_name}': {e}")
            return None

    def set_active_sheet(self, sheet_name):
        try:
            self.wb.Sheets(sheet_name).Activate()
            self.main_sheet = self.wb.ActiveSheet
        except Exception as e:
            print(f"Error activating sheet {sheet_name}: {e}")

    def close(self):
        if self.wb:
            try:
                self.wb.Close(SaveChanges=False)
            except:
                pass
        if self.excel_app:
            try:
                self.excel_app.Quit()
            except:
                pass
        self.wb = None
        self.excel_app = None
