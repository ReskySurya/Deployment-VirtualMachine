"""Add history models

Revision ID: 5718af1276b8
Revises: ab5b4aa27d65
Create Date: 2025-03-16 10:25:45.407304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5718af1276b8'
down_revision: Union[str, None] = 'ab5b4aa27d65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Buat ENUM baru jika belum ada
    credential_type_enum = sa.Enum('AWS', 'GCP', name='credentialtype')
    credential_type_enum.create(op.get_bind(), checkfirst=True)

    vm_status_enum = sa.Enum('CREATING', 'RUNNING', 'STOPPED', 'TERMINATED', 'FAILED', name='vmstatus')
    vm_status_enum.create(op.get_bind(), checkfirst=True)  # <-- Tambahkan ini untuk membuat ENUM

    vm_provider_enum = sa.Enum('AWS', 'GCP', name='vmprovider')
    vm_provider_enum.create(op.get_bind(), checkfirst=True)

    # Update data di tabel credentials sebelum mengubah tipe kolom
    op.execute("UPDATE credentials SET type = UPPER(type) WHERE type IN ('aws', 'gcp')")

    # Ubah tipe kolom credentials.type ke ENUM
    op.execute("ALTER TABLE credentials ALTER COLUMN type TYPE credentialtype USING type::credentialtype")

    # Hapus index lama
    op.drop_index('ix_credentials_type', table_name='credentials')

    # Tambahkan kolom provider ke tabel vms
    op.add_column('vms', sa.Column('provider', sa.Enum('AWS', 'GCP', name='vmprovider'), nullable=True))

    # Ubah tipe kolom status di tabel vms ke ENUM
    op.execute("ALTER TABLE vms ALTER COLUMN status TYPE vmstatus USING status::text::vmstatus")  # <-- Pastikan ini setelah ENUM dibuat



def downgrade() -> None:
    # Kembalikan tipe kolom 'status' di 'vms' menjadi VARCHAR
    op.alter_column('vms', 'status',
        existing_type=sa.Enum('CREATING', 'RUNNING', 'STOPPED', 'TERMINATED', 'FAILED', name='vmstatus'),
        type_=sa.VARCHAR(),
        existing_nullable=True)

    # Hapus kolom 'provider' dari tabel 'vms'
    op.drop_column('vms', 'provider')

    # Buat kembali index yang dihapus sebelumnya
    op.create_index('ix_credentials_type', 'credentials', ['type'], unique=False)

    # Kembalikan tipe kolom 'type' di 'credentials' menjadi VARCHAR
    op.alter_column('credentials', 'type',
        existing_type=sa.Enum('aws', 'gcp', name='credentialtype'),
        type_=sa.VARCHAR(),
        existing_nullable=True)

    # Hapus ENUM jika sudah tidak digunakan
    sa.Enum(name='credentialtype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='vmprovider').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='vmstatus').drop(op.get_bind(), checkfirst=True)
