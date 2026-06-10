-- Stored procedures for the Users domain (legacy T-SQL).

CREATE PROCEDURE dbo.GetUserById
    @UserId INT,
    @IncludeInactive BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Id, Username, PasswordHash, CreatedAt
    FROM Users
    WHERE Id = @UserId
      AND (@IncludeInactive = 1 OR IsActive = 1);
END
GO

CREATE PROCEDURE dbo.DeactivateUser
    @UserId INT,
    @Reason NVARCHAR(200) OUTPUT
AS
BEGIN
    UPDATE Users SET IsActive = 0 WHERE Id = @UserId;
    SET @Reason = 'deactivated';
END
GO
