from services.pdf_parser import AcademicPDFParser
from services.feature_engine import FeatureEngine
from services.clustering import AuthorshipClustering
from models import PipelineContext
import fitz

with open("test_paper.pdf", "rb") as f:
    pdf_bytes = f.read()

ctx = PipelineContext()
parser = AcademicPDFParser()
res = parser.parse(pdf_bytes, ctx)

paragraphs = res["paragraphs"]
print("Num paragraphs:", len(paragraphs))

fe = FeatureEngine()
features_res = fe.extract_all(paragraphs, ctx)
print("Features extracted:", len(features_res["valid_indices"]))

matrix = features_res["feature_matrix"]
print("Matrix shape:", matrix.shape)
print("Variances:", matrix.var(axis=0))

clustering = AuthorshipClustering(min_cluster_size=2, min_samples=2)
cluster_res = clustering.cluster(matrix, ctx)
print("Clusters:", cluster_res["clusters"])
print("Estimated authors:", cluster_res["estimated_authors"])
print("Noise:", cluster_res["noise_percentage"])
