import os
import pypandoc
import logging
import sys
from docx2pdf import convert

# Try to import win32com for WPS support
try:
    import win32com.client
except ImportError:
    win32com = None

logger = logging.getLogger(__name__)

def markdown_to_docx(markdown_content: str, output_path: str) -> str:
    """
    Convert Markdown content to a DOCX file.
    
    Args:
        markdown_content (str): The markdown text to convert.
        output_path (str): The path to save the generated DOCX file.
        
    Returns:
        str: The path to the generated file.
        
    Raises:
        RuntimeError: If pandoc is not installed or conversion fails.
    """
    try:
        # Verify pandoc is available
        # pypandoc.get_pandoc_version() will raise OSError if pandoc is not found
        try:
            pypandoc.get_pandoc_version()
        except OSError:
            logger.error("Pandoc not found. Please install Pandoc.")
            raise RuntimeError("Pandoc is not installed on the system. Cannot convert to DOCX.")

        pypandoc.convert_text(
            markdown_content, 
            'docx', 
            format='md', 
            outputfile=output_path,
            extra_args=['--reference-doc=custom-reference.docx'] if os.path.exists('custom-reference.docx') else []
        )
        return output_path
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        raise e

def convert_with_wps(docx_path: str, pdf_path: str):
    """
    Convert DOCX to PDF using WPS Office via COM interface.
    """
    if not win32com:
        raise ImportError("pywin32 is required for WPS conversion. Please install it with 'pip install pywin32'.")

    # Initialize COM
    import pythoncom
    pythoncom.CoInitialize()
    
    wps = None
    doc = None
    try:
        # Try to connect to WPS
        # "Kwps.Application" is for WPS Writer
        # "Ket.Application" is for WPS Spreadsheets
        # "Kwpp.Application" is for WPS Presentation
        try:
            wps = win32com.client.Dispatch("Kwps.Application")
        except Exception:
            # Try alternative ProgID
            wps = win32com.client.Dispatch("WPS.Application")

        if not wps:
            raise RuntimeError("Could not initialize WPS Application.")

        wps.Visible = False
        
        # Open document
        # WPS expects absolute paths with backslashes on Windows
        abs_docx_path = os.path.abspath(docx_path)
        abs_pdf_path = os.path.abspath(pdf_path)
        
        doc = wps.Documents.Open(abs_docx_path, ReadOnly=True)
        
        # Save as PDF
        # 17 is the file format constant for PDF in WPS/Word (wdFormatPDF)
        doc.ExportAsFixedFormat(
            OutputFileName=abs_pdf_path,
            ExportFormat=17, # wdFormatPDF
            OpenAfterExport=False,
            OptimizeFor=0,   # wdExportOptimizeForPrint
        )
        
    except Exception as e:
        logger.error(f"WPS Conversion Error: {e}")
        raise e
    finally:
        if doc:
            try:
                doc.Close(SaveChanges=0) # wdDoNotSaveChanges
            except:
                pass
        if wps:
            try:
                wps.Quit()
            except:
                pass
        pythoncom.CoUninitialize()

def docx_to_pdf(docx_path: str, pdf_path: str = None) -> str:
    """
    Convert a DOCX file to PDF.
    Tries Microsoft Word first, then falls back to WPS Office.
    
    Args:
        docx_path (str): The path to the input DOCX file.
        pdf_path (str, optional): The path to save the generated PDF file. 
                                  If not provided, it will be saved in the same folder with .pdf extension.
                                  
    Returns:
        str: The path to the generated PDF file.
        
    Raises:
        RuntimeError: If neither MS Word nor WPS is installed or conversion fails.
    """
    try:
        if not os.path.exists(docx_path):
            raise FileNotFoundError(f"Input file not found: {docx_path}")
            
        # If pdf_path is not provided, generate it from docx_path
        if not pdf_path:
            pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
            
        # Strategy 1: Try MS Word (via docx2pdf)
        try:
            # convert() uses 'Word.Application' COM object
            convert(docx_path, pdf_path)
            return pdf_path
        except Exception as ms_error:
            # Strategy 2: If on Windows, try WPS
            if sys.platform == 'win32':
                logger.info(f"MS Word conversion failed ({ms_error}), trying WPS...")
                try:
                    convert_with_wps(docx_path, pdf_path)
                    return pdf_path
                except Exception as wps_error:
                    error_msg = f"Conversion failed. MS Word Error: {ms_error}. WPS Error: {wps_error}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
            else:
                raise ms_error
                
    except Exception as e:
        logger.error(f"PDF Conversion failed: {e}")
        raise e
