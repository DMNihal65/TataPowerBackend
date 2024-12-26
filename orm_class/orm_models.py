from sqlalchemy import create_engine, Column, Integer, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class PartNumber(Base):
    __tablename__ = 'part_number'

    id = Column(Integer, primary_key=True)
    part_number = Column(String, unique=True)
    description = Column(String)
    is_active = Column(Boolean)
    inactive_date = Column(TIMESTAMP(timezone=False))
    created_at = Column(TIMESTAMP(timezone=False), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=False), default=func.now(), onupdate=func.now())

    documents = relationship('Document', back_populates='part_number')
    part_number_documents = relationship('PartNumberDocument', back_populates='part_number')


class FolderMaster(Base):
    __tablename__ = 'folder_master'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)
    requires_validity = Column(Boolean)
    is_mandatory = Column(Boolean)
    created_at = Column(TIMESTAMP(timezone=False), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=False), default=func.now(), onupdate=func.now())

    parent_id = Column(Integer, ForeignKey('folder_master.id'), nullable=True)  # Allow NULL values
    parent = relationship('FolderMaster', remote_side=[id], backref='children')

    documents = relationship('Document', back_populates='folder')


class Document(Base):
    __tablename__ = 'document'

    id = Column(Integer, primary_key=True)
    part_number_id = Column(Integer, ForeignKey('part_number.id'))
    folder_id = Column(Integer, ForeignKey('folder_master.id'))
    file_name = Column(String)
    file_path = Column(String)
    version = Column(Integer)
    validity_date = Column(TIMESTAMP(timezone=False))
    status = Column(String)
    created_at = Column(TIMESTAMP(timezone=False), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=False), default=func.now(), onupdate=func.now())

    part_number = relationship('PartNumber', back_populates='documents')
    folder = relationship('FolderMaster', back_populates='documents')
    document_approvals = relationship('DocumentApproval', back_populates='document')
    part_number_documents = relationship('PartNumberDocument', back_populates='document')


class DocumentApproval(Base):
    __tablename__ = 'document_approval'

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('document.id'))
    status = Column(String)
    approval_date = Column(TIMESTAMP(timezone=False))

    document = relationship('Document', back_populates='document_approvals')


class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    role = Column(String)
    password = Column(String)  # Ensure the password field is included
    created_at = Column(TIMESTAMP(timezone=False), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=False), default=func.now(), onupdate=func.now())

    notifications = relationship('Notification', back_populates='user')
    user_logs = relationship('UserLogs', back_populates='user')


class Notification(Base):
    __tablename__ = 'notification'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'))
    type = Column(String)
    message = Column(String)
    is_read = Column(Boolean)
    created_at = Column(TIMESTAMP(timezone=False), default=func.now())

    user = relationship('User', back_populates='notifications')


class PartNumberDocument(Base):
    __tablename__ = 'part_number_document'

    part_number_id = Column(Integer, ForeignKey('part_number.id'), primary_key=True)
    document_id = Column(Integer, ForeignKey('document.id'), primary_key=True)

    part_number = relationship('PartNumber', back_populates='part_number_documents')
    document = relationship('Document', back_populates='part_number_documents')


class UserLogs(Base):
    __tablename__ = 'user_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'))
    username = Column(String)  # Add this field
    email = Column(String)  # Add this field
    login_timestamp = Column(TIMESTAMP(timezone=False), default=func.now())

    user = relationship('User', back_populates='user_logs')
