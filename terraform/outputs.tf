output "ec2_public_ip" {
  description = "IP pública de la EC2 — úsala para SSH y para acceder a los servicios"
  value       = aws_instance.fraud_server.public_ip
}

output "ssh_command" {
  description = "Comando SSH listo para copiar (sustituir la ruta de tu .pem)"
  value       = "ssh -i ~/.ssh/${var.key_pair_name}.pem ubuntu@${aws_instance.fraud_server.public_ip}"
}

output "services" {
  description = "URLs de acceso a cada servicio (disponibles ~3 min después del apply)"
  value = {
    jupyter    = "http://${aws_instance.fraud_server.public_ip}:8888"
    api_docs   = "http://${aws_instance.fraud_server.public_ip}:8000/docs"
    api_health = "http://${aws_instance.fraud_server.public_ip}:8000/health"
    neo4j      = "http://${aws_instance.fraud_server.public_ip}:7474"
    hadoop_ui  = "http://${aws_instance.fraud_server.public_ip}:9870"
    yarn_ui    = "http://${aws_instance.fraud_server.public_ip}:8088"
    n8n        = "http://${aws_instance.fraud_server.public_ip}:5678"
  }
}

output "state_bucket_name" {
  description = "Nombre del bucket S3 para el Terraform state (copiar en main.tf si usas backend S3)"
  value       = aws_s3_bucket.terraform_state.bucket
}

output "logs_command" {
  description = "Comando para ver el progreso del user_data (instalacion Docker / servicios)"
  value       = "ssh -i ~/.ssh/${var.key_pair_name}.pem ubuntu@${aws_instance.fraud_server.public_ip} 'sudo tail -f /var/log/user-data.log'"
}
