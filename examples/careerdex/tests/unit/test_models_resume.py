"""Unit tests for careerdex resume models."""

from __future__ import annotations

from careerdex.models.resume import (
    Certification,
    ContactInfo,
    Education,
    Project,
    Publication,
    Resume,
    SkillGroup,
    WorkExperience,
)


class TestContactInfo:
    def test_all_defaults_empty(self) -> None:
        c = ContactInfo()
        assert c.name == ""
        assert c.email == ""
        assert c.phone == ""
        assert c.location == ""
        assert c.linkedin == ""
        assert c.github == ""
        assert c.website == ""
        assert c.title == ""

    def test_custom_fields(self) -> None:
        c = ContactInfo(
            name="Ada Lovelace",
            email="ada@example.com",
            phone="+1-555-0100",
            linkedin="https://linkedin.com/in/ada",
            github="https://github.com/ada",
        )
        assert c.name == "Ada Lovelace"
        assert c.email == "ada@example.com"
        assert c.phone == "+1-555-0100"


class TestWorkExperience:
    def test_required_fields(self) -> None:
        w = WorkExperience(company="Acme", title="Data Engineer")
        assert w.company == "Acme"
        assert w.title == "Data Engineer"

    def test_defaults(self) -> None:
        w = WorkExperience(company="Acme", title="SWE")
        assert w.location == ""
        assert w.start_date == ""
        assert w.end_date == ""
        assert w.current is False
        assert w.bullets == []
        assert w.technologies == []

    def test_full_construction(self) -> None:
        w = WorkExperience(
            company="DataCo",
            title="Senior Data Engineer",
            location="NYC",
            start_date="Jan 2022",
            end_date="Present",
            current=True,
            bullets=["Built ETL pipelines", "Reduced latency by 40%"],
            technologies=["Python", "Spark", "Airflow"],
        )
        assert w.current is True
        assert len(w.bullets) == 2
        assert "Spark" in w.technologies


class TestEducation:
    def test_required_fields(self) -> None:
        e = Education(institution="MIT", degree="BS")
        assert e.institution == "MIT"
        assert e.degree == "BS"

    def test_defaults(self) -> None:
        e = Education(institution="MIT", degree="BS")
        assert e.field == ""
        assert e.location == ""
        assert e.start_date == ""
        assert e.end_date == ""
        assert e.gpa == ""
        assert e.honors == []
        assert e.relevant_coursework == []

    def test_full_construction(self) -> None:
        e = Education(
            institution="Stanford",
            degree="MS",
            field="Computer Science",
            gpa="3.9",
            honors=["Magna Cum Laude"],
            relevant_coursework=["Databases", "ML"],
        )
        assert e.gpa == "3.9"
        assert len(e.honors) == 1
        assert "Databases" in e.relevant_coursework


class TestCertification:
    def test_required_name(self) -> None:
        c = Certification(name="AWS Solutions Architect")
        assert c.name == "AWS Solutions Architect"

    def test_defaults(self) -> None:
        c = Certification(name="GCP Pro")
        assert c.issuer == ""
        assert c.date_earned == ""
        assert c.expiry == ""
        assert c.credential_id == ""
        assert c.url == ""

    def test_full_construction(self) -> None:
        c = Certification(
            name="CKA",
            issuer="CNCF",
            date_earned="2023-06",
            expiry="2026-06",
            credential_id="CKA-12345",
            url="https://training.linuxfoundation.org",
        )
        assert c.issuer == "CNCF"
        assert c.credential_id == "CKA-12345"


class TestProject:
    def test_required_name(self) -> None:
        p = Project(name="DEX Pipeline")
        assert p.name == "DEX Pipeline"

    def test_technologies_list(self) -> None:
        p = Project(name="Lakehouse", technologies=["Delta Lake", "Spark", "dbt"])
        assert len(p.technologies) == 3
        assert "dbt" in p.technologies

    def test_defaults(self) -> None:
        p = Project(name="Test")
        assert p.description == ""
        assert p.role == ""
        assert p.url == ""
        assert p.repo == ""
        assert p.technologies == []
        assert p.highlights == []
        assert p.start_date == ""
        assert p.end_date == ""


class TestSkillGroup:
    def test_construction(self) -> None:
        sg = SkillGroup(category="Languages", skills=["Python", "SQL", "Scala"])
        assert sg.category == "Languages"
        assert len(sg.skills) == 3

    def test_empty_skills(self) -> None:
        sg = SkillGroup(category="Cloud")
        assert sg.skills == []


class TestResume:
    def test_defaults(self) -> None:
        r = Resume()
        assert r.template == "classic"
        assert r.accent_color == "#6366f1"
        assert r.font_size_pt == 10
        assert r.summary == ""
        assert r.target_role == ""
        assert r.version_label == ""
        assert r.last_updated is None

    def test_empty_lists(self) -> None:
        r = Resume()
        assert r.skills == []
        assert r.experience == []
        assert r.education == []
        assert r.certifications == []
        assert r.projects == []
        assert r.publications == []

    def test_contact_default_factory(self) -> None:
        r = Resume()
        assert isinstance(r.contact, ContactInfo)
        assert r.contact.name == ""

    def test_model_dump_round_trip(self) -> None:
        r = Resume(
            contact=ContactInfo(name="Ada", email="ada@example.com"),
            summary="Senior Data Engineer",
            skills=[SkillGroup(category="Languages", skills=["Python", "SQL"])],
            experience=[
                WorkExperience(
                    company="Acme",
                    title="Data Engineer",
                    start_date="Jan 2022",
                    bullets=["Built pipelines"],
                )
            ],
        )
        data = r.model_dump(mode="json")
        restored = Resume(**data)
        assert restored.contact.name == "Ada"
        assert restored.summary == "Senior Data Engineer"
        assert len(restored.skills) == 1
        assert restored.skills[0].category == "Languages"
        assert len(restored.experience) == 1
        assert restored.experience[0].company == "Acme"

    def test_template_values(self) -> None:
        r_classic = Resume(template="classic")
        r_compact = Resume(template="compact")
        r_modern = Resume(template="modern")
        assert r_classic.template == "classic"
        assert r_compact.template == "compact"
        assert r_modern.template == "modern"

    def test_full_construction(self) -> None:
        r = Resume(
            contact=ContactInfo(name="Bob", email="bob@example.com"),
            summary="Expert engineer",
            skills=[SkillGroup(category="Cloud", skills=["AWS", "GCP"])],
            certifications=[Certification(name="AWS SAA")],
            projects=[Project(name="Pipeline", technologies=["Spark"])],
            publications=[Publication(title="Data Lakehouse Patterns", venue="Blog")],
        )
        assert r.contact.name == "Bob"
        assert len(r.certifications) == 1
        assert len(r.projects) == 1
        assert len(r.publications) == 1
