# ─── AMI: Ubuntu 22.04 LTS más reciente ────────────────────────────────────────
data "aws_ami" "ubuntu_22" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical oficial

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ─── Security Group ─────────────────────────────────────────────────────────────
resource "aws_security_group" "fraud_sg" {
  name        = "fraud-detection-sg"
  description = "Acceso a los servicios del TFG de deteccion de fraude"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip]
  }

  ingress {
    description = "FastAPI /predict"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip]
  }

  ingress {
    description = "JupyterLab"
    from_port   = 8888
    to_port     = 8888
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip]
  }

  ingress {
    description = "Neo4j Browser"
    from_port   = 7474
    to_port     = 7474
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip]
  }

  ingress {
    description = "Neo4j Bolt"
    from_port   = 7687
    to_port     = 7687
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip]
  }

  ingress {
    description = "Hadoop NameNode UI"
    from_port   = 9870
    to_port     = 9870
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip]
  }

  ingress {
    description = "YARN ResourceManager UI"
    from_port   = 8088
    to_port     = 8088
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip]
  }

  ingress {
    description = "n8n workflows"
    from_port   = 5678
    to_port     = 5678
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip]
  }

  egress {
    description = "Todo el trafico saliente"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "fraud-detection-sg"
    Project = "TFG"
  }
}

# ─── EC2 Instance ───────────────────────────────────────────────────────────────
resource "aws_instance" "fraud_server" {
  ami                    = data.aws_ami.ubuntu_22.id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.fraud_sg.id]
  iam_instance_profile   = "LabInstanceProfile"   # Rol preexistente en AWS Academy

  root_block_device {
    volume_size           = 30      # GB — suficiente para imágenes Docker + datos
    volume_type           = "gp3"
    delete_on_termination = true
  }

  # ── user_data: se ejecuta UNA VEZ al arrancar la instancia ──────────────────
  # Progreso visible en: sudo tail -f /var/log/user-data.log
  user_data = templatefile("${path.module}/userdata.sh.tpl", {
    repo_url       = var.repo_url
    model_s3_path  = var.model_s3_path
  })

  tags = {
    Name    = "fraud-detection-server"
    Project = "TFG"
  }
}
