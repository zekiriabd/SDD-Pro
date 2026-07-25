using System;
using System.Configuration;
using System.Data;
using System.Data.SqlClient;

namespace HelloWebForms.App_Code
{
    public static class DataAccess
    {
        private static string ConnString
        {
            get { return ConfigurationManager.ConnectionStrings["AppDb"].ConnectionString; }
        }

        /// <summary>
        /// Validates a user against the Users table.
        /// Returns the User.Id if credentials match (PasswordHash compared with SHA-256 hash),
        /// or null if the username is unknown or the password is incorrect.
        /// </summary>
        public static int? ValidateUser(string username, string password)
        {
            if (string.IsNullOrWhiteSpace(username) || string.IsNullOrEmpty(password))
            {
                return null;
            }

            string hash = HashPassword(password);
            using (var conn = new SqlConnection(ConnString))
            using (var cmd = new SqlCommand(
                "SELECT Id FROM Users WHERE Username = @u AND PasswordHash = @p", conn))
            {
                cmd.Parameters.AddWithValue("@u", username);
                cmd.Parameters.AddWithValue("@p", hash);
                conn.Open();
                object result = cmd.ExecuteScalar();
                if (result == null || result == DBNull.Value)
                {
                    return null;
                }
                return Convert.ToInt32(result);
            }
        }

        private static string HashPassword(string password)
        {
            using (var sha = System.Security.Cryptography.SHA256.Create())
            {
                byte[] bytes = sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(password));
                return BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant();
            }
        }
    }
}
