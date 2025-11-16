# wfp-taxonomy-analysis

## Glossary:

1. Topic - Category of the report - https://www.wfp.org/publications?f%5B0%5D=publication_type%3A2146
2. Tag - blue boxes under each report - https://www.wfp.org/publications/evaluation-honduras-wfp-country-strategic-plan-2023-2027 - each topic can have multiple tags, with a 	   	  topic being one of the tags


### Key Steps Performed: 

1. #### Record vs. File Validation

	a. Began an initial check to ensure that the number of report records matches the number of downloaded files.

	b. Included script logic to count files within a directory structure.

2. #### Duplicate Report Detection

	a. Calculated how many unique report names exist compared to the total number of rows.

	b. Identified that some reports appear across multiple topics 

	![Repeated Records][/Users/madhu/Desktop/repeated_reports.png]

3. ### Focus on Topics - analysis.ipynb

	a. Unique Topics - 66
	
	b. We initially planned to analyze tags, but since topics recur across multiple reports and provide more consistent structure, we decided to focus our analysis on topics instead

4. ### Extract PDF Info - wfp_pdf_extraction_pipeline.py
	
	a. Used open source PDF extractor tools to extract the PDF sections 

	b. extracted text blocks with text, bbox, font size, position

	c. removed header and footers

	d. saved each pdf as a json - easier to send to the LLM

	e. created a metadata file that hold information such as Report Name, Topic, Path to JSON, page count