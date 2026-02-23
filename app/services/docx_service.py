# # app/services/docx_service.py

# from docx import Document
# from docx.shared import Inches
# from io import BytesIO


# def generate_docx(resume_data: dict, profile_image_bytes: bytes = None) -> bytes:
#     document = Document()

#     personal = resume_data.get("personal", {})
#     summary = resume_data.get("summary", "")
#     education = resume_data.get("education", [])
#     experience = resume_data.get("experience", [])
#     projects = resume_data.get("projects", [])
#     certifications = resume_data.get("certifications", [])

#     # ----------------------------
#     # Name
#     # ----------------------------
#     document.add_heading(personal.get("fullName", ""), level=1)

#     contact_line = f"{personal.get('email', '')} | {personal.get('phone', '')} | {personal.get('location', '')}"
#     document.add_paragraph(contact_line)

#     # ----------------------------
#     # Profile Image (Optional)
#     # ----------------------------
#     if profile_image_bytes:
#         image_stream = BytesIO(profile_image_bytes)
#         document.add_picture(image_stream, width=Inches(1.5))

#     # ----------------------------
#     # Summary
#     # ----------------------------
#     if summary:
#         document.add_heading("Professional Summary", level=2)
#         document.add_paragraph(summary)

#     # ----------------------------
#     # Experience
#     # ----------------------------
#     if experience:
#         document.add_heading("Experience", level=2)
#         for exp in experience:
#             document.add_paragraph(
#                 f"{exp.get('jobTitle')} - {exp.get('company')}",
#                 style="List Bullet"
#             )
#             document.add_paragraph(exp.get("description", ""))

#     # ----------------------------
#     # Projects
#     # ----------------------------
#     if projects:
#         document.add_heading("Projects", level=2)
#         for proj in projects:
#             document.add_paragraph(
#                 f"{proj.get('title')} ({proj.get('techStack')})",
#                 style="List Bullet"
#             )
#             document.add_paragraph(proj.get("description", ""))

#     # ----------------------------
#     # Education
#     # ----------------------------
#     if education:
#         document.add_heading("Education", level=2)
#         for edu in education:
#             document.add_paragraph(
#                 f"{edu.get('degree')} - {edu.get('institution')}",
#                 style="List Bullet"
#             )

#     # ----------------------------
#     # Certifications
#     # ----------------------------
#     if certifications:
#         document.add_heading("Certifications", level=2)
#         for cert in certifications:
#             document.add_paragraph(
#                 f"{cert.get('title')} - {cert.get('issuer')}",
#                 style="List Bullet"
#             )

#     # ----------------------------
#     # Save to bytes
#     # ----------------------------
#     file_stream = BytesIO()
#     document.save(file_stream)
#     file_stream.seek(0)

#     return file_stream.read()
